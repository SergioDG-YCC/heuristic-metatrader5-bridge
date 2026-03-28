#property strict
#property description "MT5 indicator enrichment service for Python requests via Common Files."

input int InpTimerSeconds = 2;
input bool InpDeleteRequestAfterProcess = true;

string ServiceLockName()
{
   return CommonRoot() + "indicator_service_lock";
}

double ServiceLockToken()
{
   return (double)ChartID();
}

bool AcquireServiceLock()
{
   string lock_name = ServiceLockName();
   double token = ServiceLockToken();
   if(!GlobalVariableCheck(lock_name))
     {
      GlobalVariableSet(lock_name, token);
      return true;
     }
   double current = GlobalVariableGet(lock_name);
   if((long)current == (long)token)
      return true;
   return GlobalVariableSetOnCondition(lock_name, token, current);
}

void ReleaseServiceLock()
{
   string lock_name = ServiceLockName();
   if(!GlobalVariableCheck(lock_name))
      return;
   double current = GlobalVariableGet(lock_name);
   if((long)current == (long)ServiceLockToken())
      GlobalVariableDel(lock_name);
}

string CommonRoot()
{
   return "llm_mt5_bridge\\";
}

string RequestDir()
{
   return CommonRoot() + "indicator_requests\\";
}

string ResponseDir()
{
   return CommonRoot() + "indicator_snapshots\\";
}

string JsonEscape(const string value)
{
   string escaped = value;
   StringReplace(escaped, "\\", "\\\\");
   StringReplace(escaped, "\"", "\\\"");
   StringReplace(escaped, "\r", "\\r");
   StringReplace(escaped, "\n", "\\n");
   StringReplace(escaped, "\t", "\\t");
   return escaped;
}

string IsoTime(const datetime value)
{
   MqlDateTime dt;
   TimeToStruct(value, dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ", dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}

string ReadFileText(const string relative_path)
{
   int handle = FileOpen(relative_path, FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
   if(handle == INVALID_HANDLE)
      return "";
   string text = "";
   while(!FileIsEnding(handle))
      text += FileReadString(handle);
   FileClose(handle);
   return text;
}

bool WriteFileText(const string relative_path, const string content)
{
   int handle = FileOpen(relative_path, FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
   if(handle == INVALID_HANDLE)
      return false;
   FileWriteString(handle, content);
   FileClose(handle);
   return true;
}

string ExtractJsonString(const string json, const string key)
{
   string pattern = "\"" + key + "\"";
   int pos = StringFind(json, pattern);
   if(pos < 0)
      return "";
   pos = StringFind(json, ":", pos);
   if(pos < 0)
      return "";
   int first_quote = StringFind(json, "\"", pos + 1);
   if(first_quote < 0)
      return "";
   int second_quote = StringFind(json, "\"", first_quote + 1);
   if(second_quote < 0)
      return "";
   return StringSubstr(json, first_quote + 1, second_quote - first_quote - 1);
}

int ExtractJsonInt(const string json, const string key)
{
   string pattern = "\"" + key + "\"";
   int pos = StringFind(json, pattern);
   if(pos < 0)
      return 0;
   pos = StringFind(json, ":", pos);
   if(pos < 0)
      return 0;
   string raw = "";
   for(int i = pos + 1; i < StringLen(json); i++)
     {
      ushort c = StringGetCharacter(json, i);
      if((c >= '0' && c <= '9') || c == '-')
         raw += StringSubstr(json, i, 1);
      else if(StringLen(raw) > 0)
         break;
     }
   return (int)StringToInteger(raw);
}

string ExtractJsonArrayRaw(const string json, const string key)
{
   string pattern = "\"" + key + "\"";
   int pos = StringFind(json, pattern);
   if(pos < 0)
      return "";
   pos = StringFind(json, "[", pos);
   if(pos < 0)
      return "";
   int end = StringFind(json, "]", pos);
   if(end < 0)
      return "";
   return StringSubstr(json, pos + 1, end - pos - 1);
}

void ParseIndicators(const string raw, string &items[])
{
   ArrayResize(items, 0);
   string work = raw;
   StringReplace(work, "\"", "");
   StringReplace(work, " ", "");
   if(StringLen(work) == 0)
      return;
   ushort comma = ',';
   int count = StringSplit(work, comma, items);
   if(count < 0)
      ArrayResize(items, 0);
}

ENUM_TIMEFRAMES ParseTimeframe(const string timeframe)
{
   string tf = timeframe;
   StringToUpper(tf);
   if(tf == "M1")
      return PERIOD_M1;
   if(tf == "M5")
      return PERIOD_M5;
   if(tf == "M15")
      return PERIOD_M15;
   if(tf == "M30")
      return PERIOD_M30;
   if(tf == "H1")
      return PERIOD_H1;
   if(tf == "H4")
      return PERIOD_H4;
   if(tf == "D1")
      return PERIOD_D1;
   return PERIOD_M5;
}

bool AppendIndicatorValue(string &json, const string name, const string symbol, const ENUM_TIMEFRAMES timeframe, const int lookback, bool &first)
{
   double value = 0.0;
   bool ok = false;
   if(!SymbolSelect(symbol, true))
      return false;

   if(name == "ema_20")
     {
      int handle = iMA(symbol, timeframe, 20, 0, MODE_EMA, PRICE_CLOSE);
      if(handle == INVALID_HANDLE) return false;
      double buffer[];
      ArraySetAsSeries(buffer, true);
      ok = (CopyBuffer(handle, 0, 0, 1, buffer) == 1);
      if(ok) value = buffer[0];
      IndicatorRelease(handle);
     }
   else if(name == "ema_50")
     {
      int handle = iMA(symbol, timeframe, 50, 0, MODE_EMA, PRICE_CLOSE);
      if(handle == INVALID_HANDLE) return false;
      double buffer[];
      ArraySetAsSeries(buffer, true);
      ok = (CopyBuffer(handle, 0, 0, 1, buffer) == 1);
      if(ok) value = buffer[0];
      IndicatorRelease(handle);
     }
   else if(name == "rsi_14")
     {
      int handle = iRSI(symbol, timeframe, 14, PRICE_CLOSE);
      if(handle == INVALID_HANDLE) return false;
      double buffer[];
      ArraySetAsSeries(buffer, true);
      ok = (CopyBuffer(handle, 0, 0, 1, buffer) == 1);
      if(ok) value = buffer[0];
      IndicatorRelease(handle);
     }
   else if(name == "atr_14")
     {
      int handle = iATR(symbol, timeframe, 14);
      if(handle == INVALID_HANDLE) return false;
      double buffer[];
      ArraySetAsSeries(buffer, true);
      ok = (CopyBuffer(handle, 0, 0, 1, buffer) == 1);
      if(ok) value = buffer[0];
      IndicatorRelease(handle);
     }
   else if(name == "macd_main" || name == "macd_signal")
     {
      int handle = iMACD(symbol, timeframe, 12, 26, 9, PRICE_CLOSE);
      if(handle == INVALID_HANDLE) return false;
      double main_buf[];
      double signal_buf[];
      ArraySetAsSeries(main_buf, true);
      ArraySetAsSeries(signal_buf, true);
      bool copied = (CopyBuffer(handle, 0, 0, 1, main_buf) == 1 && CopyBuffer(handle, 1, 0, 1, signal_buf) == 1);
      if(copied)
        {
         value = (name == "macd_main") ? main_buf[0] : signal_buf[0];
         ok = true;
        }
      IndicatorRelease(handle);
     }
   else if(name == "bars_available")
     {
      value = (double)iBars(symbol, timeframe);
      ok = true;
     }
   else if(name == "close_0")
     {
      double close_buf[];
      ArraySetAsSeries(close_buf, true);
      ok = (CopyClose(symbol, timeframe, 0, 1, close_buf) == 1);
      if(ok) value = close_buf[0];
     }

   if(!ok)
      return false;

   if(!first)
      json += ",";
   first = false;
   json += "\"" + name + "\":" + DoubleToString(value, 8);
   return true;
}

bool ProcessRequestFile(const string file_name)
{
   string request_path = RequestDir() + file_name;
   string content = ReadFileText(request_path);
   if(StringLen(content) == 0)
      return false;

   string request_id = ExtractJsonString(content, "request_id");
   string symbol = ExtractJsonString(content, "symbol");
   string timeframe_raw = ExtractJsonString(content, "timeframe");
   int lookback = ExtractJsonInt(content, "lookback");
   string indicators_raw = ExtractJsonArrayRaw(content, "requested_indicators");
   if(StringLen(request_id) == 0 || StringLen(symbol) == 0 || StringLen(timeframe_raw) == 0)
      return false;

   string indicators[];
   ParseIndicators(indicators_raw, indicators);
   ENUM_TIMEFRAMES timeframe = ParseTimeframe(timeframe_raw);

   string indicator_json = "";
   bool first = true;
   for(int i = 0; i < ArraySize(indicators); i++)
      AppendIndicatorValue(indicator_json, indicators[i], symbol, timeframe, lookback, first);

   string response =
      "{"
      "\"request_id\":\"" + JsonEscape(request_id) + "\","
      "\"symbol\":\"" + JsonEscape(symbol) + "\","
      "\"timeframe\":\"" + JsonEscape(timeframe_raw) + "\","
      "\"indicator_values\":{" + indicator_json + "},"
      "\"computed_at\":\"" + IsoTime(TimeGMT()) + "\","
      "\"source\":\"mt5_ea\""
      "}";

   string response_path = ResponseDir() + request_id + ".json";
   if(!WriteFileText(response_path, response))
      return false;

   if(InpDeleteRequestAfterProcess)
      FileDelete(request_path, FILE_COMMON);
   return true;
}

void ProcessRequests()
{
   string path = RequestDir() + "*.json";
   string file_name;
   long handle = FileFindFirst(path, file_name, FILE_COMMON);
   if(handle == INVALID_HANDLE)
      return;

   do
     {
      if(StringLen(file_name) > 0)
         ProcessRequestFile(file_name);
     }
   while(FileFindNext(handle, file_name));

   FileFindClose(handle);
}

int OnInit()
{
   EventSetTimer(InpTimerSeconds);
   Comment("LLM Indicator Service EA active");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   ReleaseServiceLock();
   Comment("");
}

void OnTimer()
{
   if(!AcquireServiceLock())
      return;
   ProcessRequests();
   ReleaseServiceLock();
}
