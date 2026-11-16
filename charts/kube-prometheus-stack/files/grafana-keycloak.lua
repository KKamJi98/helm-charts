-- Grafana-only bridge. OAuth2 (8) decrypts the cookie, jwt_authn (9) verifies
-- it and writes the provider payload; this Lua slot (12) precedes RBAC (301).
-- No JWT decoding, crypto, clock comparison, user lookup or value logging here.
local provider = "grafana-keycloak-owner"
local cookie_name = "GrafanaKeycloakIdToken"
local token_header = "x-grafana-keycloak-id-token"
local issuer = "https://sso.kkamji.net/realms/kkamji"
local client = "grafana"
local remove_headers = {
  "x-webauth-user", "x-grafana-user", "x-grafana-role", "x-grafana-existing-login",
  "x-grafana-keycloak-subject", "x-forwarded-user", "x-forwarded-email",
  "x-forwarded-groups", "x-auth-request-user", "x-auth-request-email",
  "x-auth-request-groups", "x-jwt-assertion"
}

local function number(v)
  return type(v) == "number" and v == v and v > -math.huge and v < math.huge
end

local function string_array(v)
  if type(v) ~= "table" then return false end
  local count = 0
  for k, item in pairs(v) do
    if type(k) ~= "number" or k < 1 or k % 1 ~= 0 or type(item) ~= "string" then
      return false
    end
    count = count + 1
  end
  return count == #v
end

local function audience(v)
  return v == client or (string_array(v) and #v == 1 and v[1] == client)
end

local function admin_group(v)
  if not string_array(v) then return false end
  for _, value in ipairs(v) do
    if value == "/grafana-admins" then return true end
  end
  return false
end

function envoy_on_request(handle)
  local headers = handle:headers()
  -- Remove every alternative credential before any denial or backend fallback.
  -- Browser cookies remain in the browser for Gateway; none reaches Grafana.
  local cookies = headers:get("cookie") or ""
  headers:remove(token_header)
  headers:remove("cookie")
  headers:remove("authorization")
  for _, name in ipairs(remove_headers) do headers:remove(name) end

  local function deny()
    handle:respond({[":status"] = "403", ["content-type"] = "text/plain",
      ["cache-control"] = "no-store"}, "SSO authorization failed.")
  end

  local metadata = handle:streamInfo():dynamicMetadata():get("envoy.filters.http.jwt_authn")
  local claims = type(metadata) == "table" and metadata[provider] or nil
  if type(claims) ~= "table" or not number(claims.exp) or not number(claims.iat)
      or claims.iss ~= issuer or not audience(claims.aud) or claims.typ ~= "ID"
      or type(claims.sub) ~= "string" or claims.sub == "" or not admin_group(claims.groups)
      or claims.azp ~= client then
    deny(); return
  end
  -- Native JWT copies a nonempty name; never allow IdP profile claims to rename
  -- or rewrite the existing owner. The client must have no default profile/email scope.
  if claims.name ~= nil or claims.email ~= nil or claims.preferred_username ~= nil
      or claims.given_name ~= nil or claims.family_name ~= nil then
    deny(); return
  end

  local count, token = 0, nil
  if cookies:find(",", 1, true) then deny(); return end
  for part in (cookies .. ";"):gmatch("([^;]*);") do
    local name, value = part:match("^%s*([^=;]+)=(.*)$")
    if name then
      name = name:gsub("%s+$", "")
      if name == cookie_name then count = count + 1; token = value end
    end
  end
  -- An additional raw-header reject route catches duplicates BEFORE OAuth's
  -- parseCookies map canonicalizes them. This count protects the post-OAuth input.
  if count ~= 1 or not token or not token:match("^[%w_-]+%.[%w_-]+%.[%w_-]+$") then
    deny(); return
  end
  -- Keep the canary routing selector intact here. Envoy Lua header mutation can
  -- clear the route cache; the selected route removes it at router finalization.
  headers:add(token_header, token)
end
