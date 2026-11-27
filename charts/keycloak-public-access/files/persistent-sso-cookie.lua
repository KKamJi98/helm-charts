-- Promote kkamji realm SSO login cookies (KEYCLOAK_IDENTITY, KEYCLOAK_SESSION)
-- from session-only to persistent (Max-Age=2592000, matching the 30d realm max
-- lifespan while Keycloak server-side still enforces the 7d idle timeout) when
-- Keycloak omits Max-Age (such as Google IdP broker login, which bypasses the
-- Remember Me form checkbox). Logout cookies (empty value or existing Max-Age /
-- Expires) and transient auth-flow cookies (AUTH_SESSION_ID, KC_RESTART) are
-- passed through untouched. Zero cookie/token values are ever logged.
local TARGET_COOKIES = {
  KEYCLOAK_IDENTITY = true,
  KEYCLOAK_SESSION = true,
}
local MAX_AGE_SECONDS = 2592000

local function trim(s)
  return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function is_kkamji_realm_path(lower)
  return lower:find(";%s*path%s*=%s*/realms/kkamji/") ~= nil
    or lower:find(";%s*path%s*=%s*/realms/kkamji;") ~= nil
    or lower:find(";%s*path%s*=%s*/realms/kkamji%s*$") ~= nil
end

local function maybe_persist_cookie(raw)
  local cname, cval = raw:match("^%s*([^=%s;]+)=([^;]*)")
  if not cname or not TARGET_COOKIES[cname] then
    return raw, false
  end
  local cleaned = trim(cval or "")
  if cleaned == "" or cleaned == '""' then
    return raw, false
  end
  local lower = raw:lower()
  if lower:find(";%s*max%-age%s*=") or lower:find(";%s*expires%s*=") then
    return raw, false
  end
  if not is_kkamji_realm_path(lower) then
    return raw, false
  end
  return raw .. "; Max-Age=" .. tostring(MAX_AGE_SECONDS), true
end

function envoy_on_response(response_handle)
  local headers = response_handle:headers()
  local count = headers:getNumValues("set-cookie")
  if not count or count <= 0 then
    return
  end
  local updated = {}
  local changed = false
  for i = 0, count - 1 do
    local raw = headers:getAtIndex("set-cookie", i)
    if raw then
      local next_val, did_change = maybe_persist_cookie(raw)
      if did_change then
        changed = true
      end
      updated[#updated + 1] = next_val
    end
  end
  if not changed then
    return
  end
  headers:remove("set-cookie")
  for _, v in ipairs(updated) do
    headers:add("set-cookie", v)
  end
end
