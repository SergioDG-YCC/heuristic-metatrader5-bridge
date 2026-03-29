//+------------------------------------------------------------------+
//| LLMBrokerSessionsService.mq5                                     |
//| MQL5 Service — runs in background, independent of any chart.    |
//|                                                                  |
//| Fetches SymbolInfoSessionTrade/Quote for MarketWatch symbols     |
//| and delivers them to the Python registry via TCP socket.         |
//|                                                                  |
//| INSTALL:                                                         |
//|   1. Copy to terminal_data_path()\MQL5\Services\                 |
//|   2. Compile (F7)                                                |
//|   3. Navigator > Services > right-click > Add Service            |
//|   4. Start the service                                           |
//|                                                                  |
//| NOTE: this service uses TCP sockets, not WebRequest.             |
//+------------------------------------------------------------------+
#property service
#property copyright "LLM-MT5-Bridge"
#property link      "https://github.com"
#property version   "1.00"
#property description "Background session data service. Pushes SymbolInfoSessionTrade/Quote to Python."

input int InpPythonPort      = 5561;  // Python broker-sessions TCP port
input int InpIntervalSeconds = 60;    // Pull interval in seconds (min 30)

//--- State
string g_known_generation = "";
bool   g_bootstrapped     = false;

//+------------------------------------------------------------------+
//| JSON-escape a string value                                        |
//+------------------------------------------------------------------+
string JsonEscape(const string s)
{
   string r = s;
   StringReplace(r, "\\", "\\\\");
   StringReplace(r, "\"", "\\\"");
   StringReplace(r, "\r", "\\r");
   StringReplace(r, "\n", "\\n");
   StringReplace(r, "\t", "\\t");
   return r;
}

//+------------------------------------------------------------------+
//| Send framed message: 4-byte big-endian length + UTF-8 JSON body  |
//+------------------------------------------------------------------+
bool SendFramed(int sock, const string json)
{
   uchar body[];
   StringToCharArray(json, body, 0, WHOLE_ARRAY, CP_UTF8);
   int body_len = ArraySize(body) - 1;   // exclude null terminator
   if(body_len <= 0) return false;

   uchar hdr[4];
   hdr[0] = (uchar)((body_len >> 24) & 0xFF);
   hdr[1] = (uchar)((body_len >> 16) & 0xFF);
   hdr[2] = (uchar)((body_len >>  8) & 0xFF);
   hdr[3] = (uchar)( body_len        & 0xFF);

   if(SocketSend(sock, hdr,  4)              != 4)        return false;
   if(SocketSend(sock, body, (uint)body_len) != body_len) return false;
   return true;
}

//+------------------------------------------------------------------+
//| Receive framed message: 4-byte big-endian length + body          |
//+------------------------------------------------------------------+
string RecvFramed(int sock, uint timeout_ms)
{
   uchar hdr[];
   if(SocketRead(sock, hdr, 4, timeout_ms) != 4) return "";

   uint msg_len = ((uint)hdr[0] << 24) | ((uint)hdr[1] << 16) |
                  ((uint)hdr[2] <<  8) |  (uint)hdr[3];

   if(msg_len == 0 || msg_len > 8388608)   // 8 MB safety limit
      return "";

   uchar body[];
   ArrayResize(body, (int)msg_len);

   uint received = 0;
   while(received < msg_len)
   {
      uchar chunk[];
      int n = SocketRead(sock, chunk, msg_len - received, timeout_ms);
      if(n <= 0) return "";
      ArrayCopy(body, chunk, (int)received, 0, n);
      received += (uint)n;
   }

   return CharArrayToString(body, 0, (int)msg_len, CP_UTF8);
}

//+------------------------------------------------------------------+
//| Extract a string value from flat JSON                             |
//+------------------------------------------------------------------+
string ExtractJsonString(const string json, const string key)
{
   string pat = "\"" + key + "\"";
   int pos = StringFind(json, pat);
   if(pos < 0) return "";
   pos = StringFind(json, ":", pos);
   if(pos < 0) return "";
   int q1 = StringFind(json, "\"", pos + 1);
   if(q1 < 0) return "";
   int q2 = StringFind(json, "\"", q1 + 1);
   if(q2 < 0) return "";
   return StringSubstr(json, q1 + 1, q2 - q1 - 1);
}

//+------------------------------------------------------------------+
//| Extract raw content of a JSON array by key, handling nesting     |
//+------------------------------------------------------------------+
string ExtractJsonArrayRaw(const string json, const string key)
{
   string pat = "\"" + key + "\"";
   int pos = StringFind(json, pat);
   if(pos < 0) return "";
   pos = StringFind(json, "[", pos);
   if(pos < 0) return "";

   int depth = 1;
   int i = pos + 1;
   int jlen = StringLen(json);
   while(i < jlen && depth > 0)
   {
      ushort c = StringGetCharacter(json, i);
      if(c == '[') depth++;
      else if(c == ']') depth--;
      i++;
   }
   if(depth != 0) return "";
   return StringSubstr(json, pos + 1, i - pos - 2);
}

//+------------------------------------------------------------------+
//| Parse a flat JSON array of strings into an MQL5 string array     |
//+------------------------------------------------------------------+
void ParseSymbolArray(const string json, const string key, string &out[])
{
   ArrayResize(out, 0);
   string raw = ExtractJsonArrayRaw(json, key);
   if(StringLen(raw) == 0) return;

   StringReplace(raw, " ", "");
   string parts[];
   int cnt = StringSplit(raw, ',', parts);
   if(cnt <= 0) return;

   int valid = 0;
   for(int i = 0; i < cnt; i++)
   {
      string p = parts[i];
      StringReplace(p, "\"", "");
      if(StringLen(p) > 0)
      {
         ArrayResize(out, valid + 1);
         out[valid++] = p;
      }
   }
}

//+------------------------------------------------------------------+
//| Collect symbols that are visible in the MarketWatch panel.       |
//| SymbolsTotal(true) includes symbols auto-selected by open charts |
//| but not shown in the panel. We additionally require SYMBOL_VISIBLE|
//| so we return exactly what the user sees in Market Watch.        |
//+------------------------------------------------------------------+
void GetMarketWatchSymbols(string &out[])
{
   int total = SymbolsTotal(true);   // selected (includes chart-driven)
   ArrayResize(out, 0);
   int n = 0;
   for(int i = 0; i < total; i++)
   {
      string sym = SymbolName(i, true);
      if(StringLen(sym) == 0)
         continue;
      // Only include symbols actually visible in the Market Watch panel
      if(SymbolInfoInteger(sym, SYMBOL_VISIBLE) == 0)
         continue;
      ArrayResize(out, n + 1);
      out[n++] = sym;
   }
}

//+------------------------------------------------------------------+
//| Build the broker_sessions_pull request JSON                       |
//+------------------------------------------------------------------+
string BuildPullRequest(const string &symbols[], const string known_gen)
{
   string syms = "[";
   for(int i = 0; i < ArraySize(symbols); i++)
   {
      if(i > 0) syms += ",";
      syms += "\"" + JsonEscape(symbols[i]) + "\"";
   }
   syms += "]";

   string gen = (StringLen(known_gen) > 0)
                ? ("\"" + JsonEscape(known_gen) + "\"")
                : "null";

   return "{\"action\":\"broker_sessions_pull\",\"symbols\":" + syms
          + ",\"known_generation\":" + gen + "}";
}

//+------------------------------------------------------------------+
//| Fetch SymbolInfoSessionTrade + Quote for each requested symbol   |
//+------------------------------------------------------------------+
string FetchAllSessions(const string &symbols[])
{
   string json = "{\"sessions\":{";
   bool first_sym = true;

   for(int s = 0; s < ArraySize(symbols); s++)
   {
      string sym = symbols[s];
      SymbolSelect(sym, true);

      if(!first_sym) json += ",";
      first_sym = false;

      json += "\"" + JsonEscape(sym) + "\":{";

      //--- Trade sessions (day 0=Sunday ... 6=Saturday)
      json += "\"trade\":{";
      for(int day = 0; day <= 6; day++)
      {
         if(day > 0) json += ",";
         json += "\"" + IntegerToString(day) + "\":[";
         bool first_sess = true;
         for(uint si = 0; si < 10; si++)
         {
            datetime dfrom = 0, dto = 0;
            if(!SymbolInfoSessionTrade(sym, (ENUM_DAY_OF_WEEK)day, si, dfrom, dto))
               break;
            if(!first_sess) json += ",";
            first_sess = false;
            json += "{\"from\":" + IntegerToString((int)dfrom)
                  + ",\"to\":"   + IntegerToString((int)dto) + "}";
         }
         json += "]";
      }
      json += "},";

      //--- Quote sessions
      json += "\"quote\":{";
      for(int day = 0; day <= 6; day++)
      {
         if(day > 0) json += ",";
         json += "\"" + IntegerToString(day) + "\":[";
         bool first_sess = true;
         for(uint si = 0; si < 10; si++)
         {
            datetime qfrom = 0, qto = 0;
            if(!SymbolInfoSessionQuote(sym, (ENUM_DAY_OF_WEEK)day, si, qfrom, qto))
               break;
            if(!first_sess) json += ",";
            first_sess = false;
            json += "{\"from\":" + IntegerToString((int)qfrom)
                  + ",\"to\":"   + IntegerToString((int)qto) + "}";
         }
         json += "]";
      }
      json += "}";   // close quote
      json += "}";   // close symbol
   }

   json += "},";

   //--- Server clock data (added once, outside per-symbol loop)
   json += "\"server_time\":" + IntegerToString((long)TimeTradeServer())
         + ",\"gmt_offset\":"  + IntegerToString((int)TimeGMTOffset())
         + "}";
   return json;
}

//+------------------------------------------------------------------+
//| One pull cycle: connect → ask Python → optionally fetch → ack   |
//| Returns true on clean exchange (even if noop).                   |
//+------------------------------------------------------------------+
bool DoPull()
{
   string mw_syms[];
   GetMarketWatchSymbols(mw_syms);
   if(ArraySize(mw_syms) == 0)
      return false;

   int sock = SocketCreate(SOCKET_DEFAULT);
   if(sock == INVALID_HANDLE)
   {
      Print("[BrokerSessions] SocketCreate failed err=", GetLastError());
      return false;
   }

   if(!SocketConnect(sock, "127.0.0.1", (uint)InpPythonPort, 5000))
   {
      if(!g_bootstrapped)
         Print("[BrokerSessions] Cannot connect to Python on port ", InpPythonPort,
               " — ensure server is running and 127.0.0.1 is allowed. err=", GetLastError());
      SocketClose(sock);
      return false;
   }

   //--- Step 1: send pull request
   if(!SendFramed(sock, BuildPullRequest(mw_syms, g_known_generation)))
   {
      Print("[BrokerSessions] SendFramed(pull) failed err=", GetLastError());
      SocketClose(sock);
      return false;
   }

   //--- Step 2: read Python's decision
   string resp = RecvFramed(sock, 10000);
   if(StringLen(resp) == 0)
   {
      Print("[BrokerSessions] Empty or timeout reading Python response");
      SocketClose(sock);
      return false;
   }

   string action = ExtractJsonString(resp, "action");

   if(action == "noop")
   {
      SocketClose(sock);
      return true;
   }

   if(action == "fetch_sessions")
   {
      string req_syms[];
      ParseSymbolArray(resp, "symbols", req_syms);
      int req_cnt = ArraySize(req_syms);

      if(req_cnt == 0)
      {
         Print("[BrokerSessions] fetch_sessions received but symbol list is empty");
         SocketClose(sock);
         return false;
      }

      //--- Step 3: fetch sessions and send payload
      string payload = FetchAllSessions(req_syms);
      if(!SendFramed(sock, payload))
      {
         Print("[BrokerSessions] SendFramed(sessions) failed err=", GetLastError());
         SocketClose(sock);
         return false;
      }

      //--- Step 4: wait for ack
      string ack        = RecvFramed(sock, 20000);
      string ack_action = ExtractJsonString(ack, "action");

      if(ack_action == "ack")
      {
         string new_gen = ExtractJsonString(ack, "generation");
         if(StringLen(new_gen) > 0)
            g_known_generation = new_gen;

         if(!g_bootstrapped)
         {
            Print("[BrokerSessions] Bootstrap complete — ", req_cnt,
                  " symbol(s), generation=", g_known_generation);
            g_bootstrapped = true;
         }
      }
      else
      {
         Print("[BrokerSessions] Unexpected ack='", ack_action, "' raw=", ack);
      }
   }
   else
   {
      Print("[BrokerSessions] Unknown action from Python: '", action, "'");
   }

   SocketClose(sock);
   return true;
}

//+------------------------------------------------------------------+
//| Service entry point — runs until MT5 stops the service           |
//+------------------------------------------------------------------+
void OnStart()
{
   int interval_ms = MathMax(InpIntervalSeconds, 30) * 1000;
   Print("[BrokerSessions] Service started — port=", InpPythonPort,
         " interval=", InpIntervalSeconds, "s");

   DoPull();   // immediate attempt on start

   while(!IsStopped())
   {
      Sleep(interval_ms);
      if(IsStopped()) break;
      DoPull();
   }

   Print("[BrokerSessions] Service stopped.");
}
//+------------------------------------------------------------------+
