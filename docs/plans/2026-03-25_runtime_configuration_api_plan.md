# Plan: Runtime Configuration API

**Fecha**: 2026-03-25  
**Objetivo**: Exponer configuración runtime vía API HTTP para modificación desde WebUI, incluyendo descubrimiento y cambio de modelos LLM.

---

## Problema Actual

Los componentes tienen valores hardcodeados o solo modificables vía `.env`:

1. **SMC LLM Validator**: `max_tokens`, `temperature`, `model` requieren restart
2. **SMC Desk**: `analyst_cooldown` hardcodeado
3. **Ownership**: `auto_adopt_foreign` hardcodeado
4. **Fast Desk**: Nuevos flags sin alias legacy
5. **LLM Models**: No hay descubrimiento de modelos disponibles en LocalAI
6. **WebUI**: No puede modificar configuración sin restart del servicio

---

## Solución Propuesta

### Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│  WebUI (Solid.js)                                                │
│  - Settings Screen                                               │
│  - LLM Model Selector                                            │
│  - Risk Config Sliders                                           │
│  - Desk Configuration Panels                                     │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ HTTP API
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Control Plane (:8765)                                           │
│  NEW ENDPOINTS:                                                  │
│  GET  /api/v1/config/smc                                         │
│  PUT  /api/v1/config/smc                                         │
│  GET  /api/v1/config/fast                                        │
│  PUT  /api/v1/config/fast                                        │
│  GET  /api/v1/config/ownership                                   │
│  PUT  /api/v1/config/ownership                                   │
│  GET  /api/v1/config/risk                                        │
│  PUT  /api/v1/config/risk                                        │
│  GET  /api/v1/llm/models                                         │
│  PUT  /api/v1/llm/models/default                                 │
│  GET  /api/v1/llm/status                                         │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ In-Memory Update
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  CoreRuntimeService                                              │
│  - smc_desk_config (mutable)                                     │
│  - fast_desk_config (mutable)                                    │
│  - ownership_registry (reconfigurable)                           │
│  - risk_kernel (reconfigurable)                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Fases de Implementación

### **Phase 1: Infrastructure & LLM Discovery**

**Objetivo**: Crear endpoints base y descubrimiento de modelos LLM.

#### Step 1.1: LLM Model Discovery Service

**Archivo**: `src/heuristic_mt5_bridge/core/llm/model_discovery.py` (nuevo)

```python
"""
LLM Model Discovery — queries LocalAI for available models.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMModel:
    id: str
    name: str
    size: str | None = None
    format: str | None = None
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None


class LLMModelDiscovery:
    def __init__(self, localai_base_url: str = "http://127.0.0.1:8080") -> None:
        self.base_url = localai_base_url.rstrip("/")

    def list_models(self) -> list[LLMModel]:
        """GET /v1/models from LocalAI."""
        try:
            request = urllib.request.Request(
                url=f"{self.base_url}/v1/models",
                headers={"Content-Type": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=10) as resp:
                body = resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"LocalAI unavailable: {exc}") from exc

        result = json.loads(body)
        models = []
        for item in result.get("data", []):
            models.append(
                LLMModel(
                    id=item.get("id", ""),
                    name=item.get("name", item.get("id", "")),
                    size=item.get("size", ""),
                    format=item.get("format", ""),
                    family=item.get("family", ""),
                    parameter_size=item.get("parameter_size", ""),
                    quantization=item.get("quantization", ""),
                )
            )
        return models

    def get_default_model(self) -> str | None:
        """Get current default model from LocalAI config."""
        try:
            request = urllib.request.Request(
                url=f"{self.base_url}/v1/config",
                headers={"Content-Type": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=10) as resp:
                body = resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError):
            return None

        result = json.loads(body)
        return result.get("default_model")

    def set_default_model(self, model_id: str) -> bool:
        """Set default model in LocalAI config."""
        try:
            payload = json.dumps({"default_model": model_id}).encode("utf-8")
            request = urllib.request.Request(
                url=f"{self.base_url}/v1/config",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with urllib.request.urlopen(request, timeout=10) as resp:
                return resp.status == 200
        except (urllib.error.URLError, TimeoutError):
            return False
```

#### Step 1.2: Control Plane Endpoints — LLM Discovery

**Archivo**: `apps/control_plane.py`

Agregar endpoints:

```python
@app.get("/api/v1/llm/models")
async def list_llm_models() -> dict[str, Any]:
    """List available LLM models from LocalAI."""
    from heuristic_mt5_bridge.core.llm.model_discovery import LLMModelDiscovery
    
    discovery = LLMModelDiscovery(
        localai_base_url=os.getenv("LOCALAI_BASE_URL", "http://127.0.0.1:8080")
    )
    try:
        models = discovery.list_models()
        return {
            "status": "success",
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "size": m.size,
                    "format": m.format,
                    "family": m.family,
                    "parameter_size": m.parameter_size,
                    "quantization": m.quantization,
                }
                for m in models
            ],
            "count": len(models),
        }
    except RuntimeError as exc:
        return {
            "status": "error",
            "error": str(exc),
            "models": [],
            "count": 0,
        }


@app.get("/api/v1/llm/status")
async def llm_status() -> dict[str, Any]:
    """Get LLM service status and current configuration."""
    from heuristic_mt5_bridge.core.llm.model_discovery import LLMModelDiscovery
    
    discovery = LLMModelDiscovery(
        localai_base_url=os.getenv("LOCALAI_BASE_URL", "http://127.0.0.1:8080")
    )
    
    # Try to get default model
    default_model = discovery.get_default_model()
    current_model = os.getenv("SMC_LLM_MODEL", "gemma-3-4b-it-qat")
    
    return {
        "status": "success",
        "localai_url": discovery.base_url,
        "default_model": default_model,
        "current_model": current_model,
        "llm_enabled": os.getenv("SMC_LLM_ENABLED", "true").lower() in ("1", "true", "yes"),
    }


@app.put("/api/v1/llm/models/default")
async def set_default_llm_model(request: Request) -> dict[str, Any]:
    """Set default LLM model in LocalAI config."""
    from heuristic_mt5_bridge.core.llm.model_discovery import LLMModelDiscovery
    
    try:
        body = await request.json()
        model_id = body.get("model_id")
        if not model_id:
            raise HTTPException(status_code=400, detail="model_id required")
        
        discovery = LLMModelDiscovery(
            localai_base_url=os.getenv("LOCALAI_BASE_URL", "http://127.0.0.1:8080")
        )
        success = discovery.set_default_model(model_id)
        
        if success:
            # Update runtime config if service is running
            if _service and _service.smc_desk_config:
                _service.smc_desk_config.llm_model = model_id
            
            return {"status": "success", "model_id": model_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to set default model")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
```

---

### **Phase 2: SMC Desk Configuration API**

**Objetivo**: Exponer configuración SMC Desk vía API.

#### Step 2.1: Config Dataclass Serializable

**Archivo**: `src/heuristic_mt5_bridge/smc_desk/analyst/heuristic_analyst.py`

Agregar métodos de serialización:

```python
@dataclass
class SmcAnalystConfig:
    # ... existing fields ...
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize config to dict for API response."""
        return {
            "max_candidates": self.max_candidates,
            "min_rr": self.min_rr,
            "next_review_hint_seconds": self.next_review_hint_seconds,
            "d1_bars": self.d1_bars,
            "h4_bars": self.h4_bars,
            "h1_bars": self.h1_bars,
            "llm_enabled": self.llm_enabled,
            "llm_model": self.llm_model,
            "llm_timeout_seconds": self.llm_timeout_seconds,
            "llm_max_tokens": getattr(self, "llm_max_tokens", 500),
            "llm_temperature": getattr(self, "llm_temperature", 0.1),
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SmcAnalystConfig":
        """Create config from dict (API request)."""
        return cls(
            max_candidates=int(data.get("max_candidates", 3)),
            min_rr=float(data.get("min_rr", 2.0)),
            next_review_hint_seconds=int(data.get("next_review_hint_seconds", 14400)),
            d1_bars=int(data.get("d1_bars", 100)),
            h4_bars=int(data.get("h4_bars", 200)),
            h1_bars=int(data.get("h1_bars", 300)),
            llm_enabled=bool(data.get("llm_enabled", True)),
            llm_model=str(data.get("llm_model", "gemma-3-4b-it-qat")),
            llm_timeout_seconds=int(data.get("llm_timeout_seconds", 60)),
            llm_max_tokens=int(data.get("llm_max_tokens", 500)),
            llm_temperature=float(data.get("llm_temperature", 0.1)),
        )
```

#### Step 2.2: Control Plane Endpoints — SMC Config

**Archivo**: `apps/control_plane.py`

```python
@app.get("/api/v1/config/smc")
async def get_smc_config() -> dict[str, Any]:
    """Get current SMC Desk configuration."""
    if not _service or not _service.smc_desk_config:
        return {
            "status": "not_configured",
            "config": {},
        }
    
    return {
        "status": "success",
        "config": _service.smc_desk_config.to_dict(),
    }


@app.put("/api/v1/config/smc")
async def update_smc_config(request: Request) -> dict[str, Any]:
    """Update SMC Desk configuration at runtime."""
    from heuristic_mt5_bridge.smc_desk.analyst.heuristic_analyst import SmcAnalystConfig
    
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        body = await request.json()
        new_config = SmcAnalystConfig.from_dict(body)
        
        # Update runtime config
        _service.smc_desk_config = new_config
        
        # Persist to .env (optional, for restart persistence)
        # TODO: Implement .env update utility
        
        return {
            "status": "success",
            "config": new_config.to_dict(),
            "message": "SMC configuration updated (runtime only, restart to persist to .env)",
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid config value: {exc}")
```

---

### **Phase 3: Fast Desk Configuration API**

**Objetivo**: Exponer configuración Fast Desk vía API.

#### Step 3.1: FastDeskConfig Serializable

**Archivo**: `src/heuristic_mt5_bridge/fast_desk/runtime.py`

Agregar métodos de serialización (similar a SMC):

```python
@dataclass
class FastDeskConfig:
    # ... existing fields ...
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_interval": self.scan_interval,
            "guard_interval": self.guard_interval,
            "signal_cooldown": self.signal_cooldown,
            "risk_per_trade_percent": self.risk_per_trade_percent,
            "max_positions_per_symbol": self.max_positions_per_symbol,
            "max_positions_total": self.max_positions_total,
            "min_signal_confidence": self.min_signal_confidence,
            "atr_multiplier_sl": self.atr_multiplier_sl,
            "rr_ratio": self.rr_ratio,
            "spread_max_pips": self.spread_max_pips,
            "max_slippage_points": self.max_slippage_points,
            "require_h1_alignment": self.require_h1_alignment,
            "enable_pending_orders": self.enable_pending_orders,
            "enable_structural_trailing": self.enable_structural_trailing,
            "enable_atr_trailing": self.enable_atr_trailing,
            "enable_scale_out": self.enable_scale_out,
            "pending_ttl_seconds": self.pending_ttl_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FastDeskConfig":
        return cls(**data)
```

#### Step 3.2: Control Plane Endpoints — Fast Config

**Archivo**: `apps/control_plane.py`

```python
@app.get("/api/v1/config/fast")
async def get_fast_config() -> dict[str, Any]:
    """Get current Fast Desk configuration."""
    if not _service or not _service.fast_desk_config:
        return {"status": "not_configured", "config": {}}
    
    return {
        "status": "success",
        "config": _service.fast_desk_config.to_dict(),
    }


@app.put("/api/v1/config/fast")
async def update_fast_config(request: Request) -> dict[str, Any]:
    """Update Fast Desk configuration at runtime."""
    from heuristic_mt5_bridge.fast_desk.runtime import FastDeskConfig
    
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        body = await request.json()
        new_config = FastDeskConfig.from_dict(body)
        _service.fast_desk_config = new_config
        
        return {
            "status": "success",
            "config": new_config.to_dict(),
            "message": "Fast Desk configuration updated (runtime only)",
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
```

---

### **Phase 4: Ownership & Risk Configuration API**

**Objetivo**: Exponer Ownership y RiskKernel vía API.

#### Step 4.1: OwnershipRegistry Reconfigurable

**Archivo**: `src/heuristic_mt5_bridge/core/ownership/registry.py`

```python
@dataclass
class OwnershipRegistry:
    # ... existing fields ...
    
    def reconfigure(self, *, auto_adopt_foreign: bool | None = None, history_retention_days: int | None = None) -> None:
        """Update configuration at runtime."""
        if auto_adopt_foreign is not None:
            self.auto_adopt_foreign = auto_adopt_foreign
        if history_retention_days is not None:
            self.history_retention_days = history_retention_days
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "auto_adopt_foreign": self.auto_adopt_foreign,
            "history_retention_days": self.history_retention_days,
            "broker_server": self.broker_server,
            "account_login": self.account_login,
        }
```

#### Step 4.2: RiskKernel Reconfigurable

**Archivo**: `src/heuristic_mt5_bridge/core/risk/kernel.py`

```python
@dataclass
class RiskKernel:
    # ... existing fields ...
    
    def reconfigure(
        self,
        *,
        profile_global: int | None = None,
        profile_fast: int | None = None,
        profile_smc: int | None = None,
        fast_budget_weight: float | None = None,
        smc_budget_weight: float | None = None,
        kill_switch_enabled: bool | None = None,
    ) -> None:
        """Update configuration at runtime."""
        if profile_global is not None:
            self.profile_global = _clamp_profile(profile_global)
        if profile_fast is not None:
            self.profile_fast = _clamp_profile(profile_fast)
        if profile_smc is not None:
            self.profile_smc = _clamp_profile(profile_smc)
        if fast_budget_weight is not None:
            self.fast_budget_weight = max(0.01, fast_budget_weight)
        if smc_budget_weight is not None:
            self.smc_budget_weight = max(0.01, smc_budget_weight)
        if kill_switch_enabled is not None:
            self.kill_switch_enabled = kill_switch_enabled
        
        # Persist changes
        self._persist_profile_state()
        self._append_event("config_updated", reason="api_reconfiguration")
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_global": self.profile_global,
            "profile_fast": self.profile_fast,
            "profile_smc": self.profile_smc,
            "fast_budget_weight": self.fast_budget_weight,
            "smc_budget_weight": self.smc_budget_weight,
            "kill_switch_enabled": self.kill_switch_enabled,
            "overrides": self.overrides,
        }
```

#### Step 4.3: Control Plane Endpoints — Ownership & Risk

**Archivo**: `apps/control_plane.py`

```python
@app.get("/api/v1/config/ownership")
async def get_ownership_config() -> dict[str, Any]:
    """Get current Ownership Registry configuration."""
    if not _service or not _service.ownership_registry:
        return {"status": "not_configured", "config": {}}
    
    return {
        "status": "success",
        "config": _service.ownership_registry.to_dict(),
    }


@app.put("/api/v1/config/ownership")
async def update_ownership_config(request: Request) -> dict[str, Any]:
    """Update Ownership Registry configuration at runtime."""
    if not _service or not _service.ownership_registry:
        raise HTTPException(status_code=503, detail="Ownership registry not initialized")
    
    try:
        body = await request.json()
        _service.ownership_registry.reconfigure(
            auto_adopt_foreign=body.get("auto_adopt_foreign"),
            history_retention_days=body.get("history_retention_days"),
        )
        
        return {
            "status": "success",
            "config": _service.ownership_registry.to_dict(),
            "message": "Ownership configuration updated",
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")


@app.get("/api/v1/config/risk")
async def get_risk_config() -> dict[str, Any]:
    """Get current RiskKernel configuration."""
    if not _service or not _service.risk_kernel:
        return {"status": "not_configured", "config": {}}
    
    return {
        "status": "success",
        "config": _service.risk_kernel.to_dict(),
    }


@app.put("/api/v1/config/risk")
async def update_risk_config(request: Request) -> dict[str, Any]:
    """Update RiskKernel configuration at runtime."""
    if not _service or not _service.risk_kernel:
        raise HTTPException(status_code=503, detail="RiskKernel not initialized")
    
    try:
        body = await request.json()
        _service.risk_kernel.reconfigure(
            profile_global=body.get("profile_global"),
            profile_fast=body.get("profile_fast"),
            profile_smc=body.get("profile_smc"),
            fast_budget_weight=body.get("fast_budget_weight"),
            smc_budget_weight=body.get("smc_budget_weight"),
            kill_switch_enabled=body.get("kill_switch_enabled"),
        )
        
        return {
            "status": "success",
            "config": _service.risk_kernel.to_dict(),
            "message": "RiskKernel configuration updated",
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
```

---

### **Phase 5: WebUI Settings Screen**

**Objetivo**: Crear pantalla de configuración en WebUI.

#### Step 5.1: Settings Route Structure

**Archivo**: `docs/webui/qwen/WEBUI_WIREFRAME_SPEC.md` (actualizar)

Agregar nueva sección para `/settings`:

```markdown
## Screen 9: Settings (Updated)

**Route**: `/settings`

### New Sections

#### LLM Configuration Panel
- Model selector dropdown (from `/api/v1/llm/models`)
- Current model display
- Max tokens slider (100-2000)
- Temperature slider (0.0-1.0)
- Timeout slider (10-300 seconds)
- [Test Connection] button
- [Save Changes] button

#### SMC Desk Configuration Panel
- Max candidates slider (1-10)
- Min R:R input (1.0-10.0)
- Review interval selector (1h, 4h, 12h, 24h)
- D1/H4/H1 bars inputs
- LLM enabled toggle
- [Save Changes] button

#### Fast Desk Configuration Panel
- Scan interval slider (1-60 seconds)
- Custody interval slider (1-10 seconds)
- Signal cooldown slider (30-300 seconds)
- Risk per trade slider (0.1-5.0%)
- Max positions per symbol (1-5)
- Max positions total (1-20)
- Min confidence slider (0.3-0.9)
- ATR multiplier SL (1.0-3.0)
- R:R ratio (1.0-10.0)
- Spread max pips (0.5-10.0)
- Max slippage points (10-100)
- H1 alignment toggle
- Pending orders toggle
- Structural trailing toggle
- ATR trailing toggle
- Scale-out toggle
- Pending TTL (minutes)
- [Save Changes] button

#### Ownership Configuration Panel
- Auto-adopt foreign positions toggle
- History retention days (7-365)
- [Save Changes] button

#### Risk Configuration Panel
- Global profile selector (1-4: Low/Medium/High/Chaos)
- Fast Desk profile selector (1-4)
- SMC Desk profile selector (1-4)
- Fast budget weight slider (0.5-2.0)
- SMC budget weight slider (0.5-2.0)
- Kill switch enabled toggle
- [Save Changes] button
```

---

## API Contract Summary

### New Endpoints

| Method | Route | Purpose | Auth |
|--------|-------|---------|------|
| `GET` | `/api/v1/llm/models` | List available LLM models | None |
| `GET` | `/api/v1/llm/status` | LLM service status | None |
| `PUT` | `/api/v1/llm/models/default` | Set default model | None |
| `GET` | `/api/v1/config/smc` | Get SMC config | None |
| `PUT` | `/api/v1/config/smc` | Update SMC config | None |
| `GET` | `/api/v1/config/fast` | Get Fast config | None |
| `PUT` | `/api/v1/config/fast` | Update Fast config | None |
| `GET` | `/api/v1/config/ownership` | Get Ownership config | None |
| `PUT` | `/api/v1/config/ownership` | Update Ownership config | None |
| `GET` | `/api/v1/config/risk` | Get Risk config | None |
| `PUT` | `/api/v1/config/risk` | Update Risk config | None |

### Response Format

**Success**:
```json
{
  "status": "success",
  "config": { ... },
  "message": "Configuration updated (runtime only)"
}
```

**Error**:
```json
{
  "status": "error",
  "error": "Error message",
  "details": { ... }
}
```

---

## Implementation Order

1. **Phase 1** (Day 1):
   - Step 1.1: Create `model_discovery.py`
   - Step 1.2: Add LLM endpoints to control plane
   - Test: `curl http://localhost:8765/api/v1/llm/models`

2. **Phase 2** (Day 2):
   - Step 2.1: Add serialization to `SmcAnalystConfig`
   - Step 2.2: Add SMC config endpoints
   - Test: `curl -X PUT http://localhost:8765/api/v1/config/smc -d '{...}'`

3. **Phase 3** (Day 3):
   - Step 3.1: Add serialization to `FastDeskConfig`
   - Step 3.2: Add Fast config endpoints
   - Test: `curl -X PUT http://localhost:8765/api/v1/config/fast -d '{...}'`

4. **Phase 4** (Day 4):
   - Step 4.1: Add `reconfigure()` to `OwnershipRegistry`
   - Step 4.2: Add `reconfigure()` to `RiskKernel`
   - Step 4.3: Add ownership/risk endpoints
   - Test: `curl -X PUT http://localhost:8765/api/v1/config/risk -d '{...}'`

5. **Phase 5** (Day 5-7):
   - Step 5.1: Update WebUI wireframes
   - Implement Settings screen in Solid.js
   - Test: UI → API integration

---

## Testing Checklist

### Phase 1 Tests
- [ ] `GET /api/v1/llm/models` returns model list
- [ ] `GET /api/v1/llm/status` returns status
- [ ] `PUT /api/v1/llm/models/default` changes default
- [ ] Error handling when LocalAI is down

### Phase 2 Tests
- [ ] `GET /api/v1/config/smc` returns current config
- [ ] `PUT /api/v1/config/smc` updates runtime config
- [ ] Invalid values return 400 error
- [ ] Config changes take effect immediately

### Phase 3 Tests
- [ ] `GET /api/v1/config/fast` returns current config
- [ ] `PUT /api/v1/config/fast` updates runtime config
- [ ] Worker picks up new config without restart

### Phase 4 Tests
- [ ] `GET /api/v1/config/ownership` returns config
- [ ] `PUT /api/v1/config/ownership` updates registry
- [ ] `GET /api/v1/config/risk` returns risk config
- [ ] `PUT /api/v1/config/risk` updates kernel
- [ ] Risk changes affect new entries immediately

### Phase 5 Tests
- [ ] Settings screen loads all configs
- [ ] Model selector populates from API
- [ ] Sliders reflect current values
- [ ] Save buttons call correct endpoints
- [ ] Success/error messages display
- [ ] Changes persist across page refresh (runtime)

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Runtime config lost on restart | Medium | Add `.env` persistence utility (Phase 6) |
| Invalid config breaks desk | High | Validate all inputs, keep sane defaults |
| LLM API changes | Low | Abstract discovery behind interface |
| Concurrent config updates | Medium | Use locks in `CoreRuntimeService` |
| WebUI shows stale config | Low | Implement polling or SSE for config changes |

---

## Phase 6 (Future): Persistence to .env

**Objetivo**: Persistir cambios runtime a `.env` para sobrevivir restarts.

```python
def update_env_file(key: str, value: str, env_path: Path = None) -> bool:
    """Update .env file with new value."""
    if env_path is None:
        env_path = repo_root_from(__file__) / ".env"
    
    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    
    if not found:
        new_lines.append(f"{key}={value}")
    
    env_path.write_text("\n".join(new_lines), encoding="utf-8")
    return found
```

---

## Criterios de Aceptación

1. ✅ Todos los endpoints responden correctamente
2. ✅ Config changes se aplican sin restart
3. ✅ WebUI puede leer/escribir configuración
4. ✅ Modelos LLM se descubren automáticamente
5. ✅ Invalid config retorna 400 con mensaje claro
6. ✅ Tests de integración pasan

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-25  
**Author**: Senior Backend Architect (AI-Assisted)  
**Reviewers**: Pending
