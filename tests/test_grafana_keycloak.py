"""Grafana v2 offline contracts; all identity fixtures are synthetic.

HELM=/path/to/helm uv run --no-project --with pyyaml --with jsonschema --with jmespath \
  --with lupa python -m unittest discover -s tests -p test_grafana_keycloak.py -v
"""
import configparser
import functools
import hashlib
import os
from pathlib import Path
import subprocess
import unittest
import copy
import re
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/kube-prometheus-stack"
HELM = os.environ.get("HELM", "helm")
ISSUER = "https://sso.kkamji.net/realms/kkamji"
TOKEN_HEADER = "X-Grafana-Keycloak-Id-Token"
COOKIE = "GrafanaKeycloakIdToken"
PROVIDER = "grafana-keycloak-owner"
READY = ["--set", "keycloakSSO.backendTLSReady=true", "--set", "keycloakSSO.grafana.dataPreservationReady=true",
         "--set", "keycloakSSO.grafana.accessLogsSafe=true"]

@functools.lru_cache(maxsize=None)
def render(mode="legacy", *extra):
    args = [HELM, "template", "kube-prometheus-stack", str(CHART), "-n", "monitoring",
            "--skip-tests", "--kube-version", "1.36.1", "-f", str(CHART / "kkamji_local_values.yaml")]
    if mode != "legacy":
        args += ["-f", str(CHART / "keycloak-canary-values.yaml"), *READY]
    if mode == "only":
        args += ["-f", str(CHART / "keycloak-only-values.yaml"), "--set", "keycloakSSO.grafana.cutoverApproved=true"]
    return subprocess.run([*args, *extra], capture_output=True, text=True, check=False, timeout=90)


def objects(mode="legacy", *extra):
    result = render(mode, *extra)
    if result.returncode:
        raise AssertionError("Helm render refused (stderr sha256=" + hashlib.sha256(result.stderr.encode()).hexdigest() + ")")
    try:
        return {(d["kind"], d["metadata"]["name"]): d for d in yaml.safe_load_all(result.stdout) if d}
    except yaml.YAMLError:
        raise AssertionError("Helm YAML parse refused (render withheld)") from None


def grafana_ini(objs):
    cm, = [d for (k, _), d in objs.items() if k == "ConfigMap" and "grafana.ini" in d.get("data", {})]
    ini = configparser.ConfigParser(interpolation=None)
    ini.read_string(cm["data"]["grafana.ini"])
    return ini


class NativeJWTTests(unittest.TestCase):
    def test_native_jwt_uses_only_private_identity_refs_and_preserves_legacy_canary(self):
        for mode in ("canary", "only"):
            with self.subTest(mode=mode):
                objs = objects(mode)
                ini = grafana_ini(objs)
                jwt = ini["auth.jwt"]
                self.assertTrue(jwt.getboolean("enabled"), "v2 requires native JWT, not Generic OAuth")
                self.assertEqual(jwt["header_name"], TOKEN_HEADER)
                self.assertEqual(jwt["username_claim"], "")
                self.assertEqual(jwt["email_claim"], "")
                self.assertEqual(jwt["email_attribute_path"], "")
                self.assertEqual(jwt["username_attribute_path"], "$__env{KEYCLOAK_GRAFANA_USERNAME_ATTRIBUTE_PATH}")
                self.assertEqual(jwt["expect_claims"], "$__env{KEYCLOAK_GRAFANA_EXPECT_CLAIMS}")
                self.assertEqual(jwt["jwk_set_url"], ISSUER + "/protocol/openid-connect/certs")
                for key in ("auto_sign_up", "url_login", "tls_skip_verify_insecure", "allow_assign_grafana_admin"):
                    self.assertFalse(jwt.getboolean(key), key)
                self.assertTrue(jwt.getboolean("skip_org_role_sync"))
                self.assertEqual(jwt["groups_attribute_path"], "")
                self.assertFalse(ini["auth.generic_oauth"].getboolean("enabled"))
                self.assertFalse(ini["auth.proxy"].getboolean("enabled"))
                self.assertFalse(ini["auth.anonymous"].getboolean("enabled"))
                self.assertFalse(ini["auth"].getboolean("oauth_allow_insecure_email_lookup"))
                self.assertTrue(ini["auth.basic"].getboolean("enabled"))
                self.assertEqual(ini["auth"].getboolean("disable_login_form"), mode == "only")
                dep, = [d for (k, n), d in objs.items() if k == "Deployment" and n.endswith("-grafana")]
                container, = [c for c in dep["spec"]["template"]["spec"]["containers"] if c["name"] == "grafana"]
                env = {e["name"]: e for e in container["env"]}
                for key, prop in (("KEYCLOAK_GRAFANA_USERNAME_ATTRIBUTE_PATH", "username_attribute_path"),
                                  ("KEYCLOAK_GRAFANA_EXPECT_CLAIMS", "expect_claims")):
                    self.assertEqual(env[key]["valueFrom"]["secretKeyRef"],
                                     {"name": "grafana-keycloak-identity", "key": prop})
                self.assertNotIn("GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET", env)
                self.assertNotIn("GF_AUTH_JWT_EXPECT_CLAIMS", env, "avoid startup env-override value logging")
                spec = objs["ExternalSecret", "grafana-keycloak-identity"]["spec"]
                self.assertEqual(spec["target"]["creationPolicy"], "Orphan")
                self.assertEqual(spec["target"]["deletionPolicy"], "Retain")
                self.assertEqual(spec["data"], [{"secretKey": prop, "remoteRef": {
                    "key": "/kkamji/keycloak/consumers/grafana", "property": prop}}
                    for prop in ("username_attribute_path", "expect_claims")])

    def test_csrf_check_remains_enabled_when_gateway_removes_browser_cookies(self):
        for mode in ("canary", "only"):
            with self.subTest(mode=mode):
                ini = grafana_ini(objects(mode))
                self.assertTrue(ini.getboolean("security", "csrf_always_check", fallback=False),
                                "CSRF checks must not depend on the cookie removed by the Gateway bridge")
                self.assertEqual(ini.get("security", "csrf_trusted_origins", fallback=""), "")
                self.assertEqual(ini.get("security", "csrf_additional_headers", fallback=""), "")

    def test_machine_bearer_has_no_browser_cookie_or_origin_authority(self):
        for mode in ("canary", "only"):
            with self.subTest(mode=mode):
                machine = objects(mode)["HTTPRoute", "grafana-machine-api"]
                removed = {name.lower() for rule in machine["spec"]["rules"]
                           for modifier in rule["filters"]
                           for name in modifier["requestHeaderModifier"]["remove"]}
                self.assertIn("origin", removed, "native Bearer clients must not inherit cookie-based CSRF origin checks")
                self.assertIn("cookie", removed)
                self.assertNotIn("authorization", removed)

    def test_csrf_bypass_settings_and_environment_overrides_are_rejected(self):
        overrides = [
            ("--set", r"kube-prometheus-stack.grafana.grafana\.ini.security.csrf_always_check=false"),
            ("--set-string", r"kube-prometheus-stack.grafana.grafana\.ini.security.csrf_trusted_origins=other.kkamji.net"),
            ("--set-string", r"kube-prometheus-stack.grafana.grafana\.ini.security.csrf_additional_headers=X-Forwarded-Host"),
            ("--set-string", "kube-prometheus-stack.grafana.env.GF_SECURITY_CSRF_ALWAYS_CHECK=false"),
            ("--set-string", "kube-prometheus-stack.grafana.env.GF_SECURITY_CSRF_TRUSTED_ORIGINS=other.kkamji.net"),
        ]
        for mode in ("canary", "only"):
            for flag, override in overrides:
                with self.subTest(mode=mode, override=override):
                    result = render(mode, flag, override)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Grafana", result.stderr)


class LuaBridgeTests(unittest.TestCase):
    def bridge(self, claims=None, header_overrides=None, metadata=None, script_override=None):
        from lupa.luajit21 import LuaRuntime
        vm = LuaRuntime()
        vm.execute("""
        function make_handle(input, md)
          local h = {values = input}
          function h:get(name) return self.values[string.lower(name)] end
          function h:remove(name) self.values[string.lower(name)] = nil end
          function h:add(name, value)
            name = string.lower(name)
            if self.values[name] then self.values[name] = self.values[name] .. "," .. value
            else self.values[name] = value end
          end
          local stream = {}
          function stream:dynamicMetadata()
            return {get = function(_, name)
              if name == "envoy.filters.http.jwt_authn" then return md end
              return nil
            end}
          end
          local r = {h = h}
          function r:headers() return self.h end
          function r:streamInfo() return stream end
          function r:respond(headers, body) self.status = headers[":status"]; self.body = body end
          function r:logInfo(_) error("token logging is forbidden") end
          function r:logWarn(_) error("token logging is forbidden") end
          return r
        end
        """)
        def table(value):
            if isinstance(value, dict):
                return vm.table_from({k: table(v) for k, v in value.items()})
            if isinstance(value, list):
                return vm.table_from([table(v) for v in value])
            return value
        if claims is None:
            claims = {"iss": ISSUER, "aud": "grafana", "sub": "synthetic-owner-sub", "typ": "ID", "azp": "grafana",
                      "exp": 2000000000, "iat": 1900000000, "groups": ["/grafana-admins"]}
        headers = {"cookie": COOKIE + "=synthetic.payload.signature; grafana_session=old-cookie",
                   "authorization": "Basic synthetic", TOKEN_HEADER.lower(): "forged-token",
                   "x-webauth-user": "forged-admin", "x-auth-request-email": "forged@example.invalid"}
        headers.update(header_overrides or {})
        script = CHART / "files/grafana-keycloak.lua"
        self.assertTrue(script.exists(), "missing native Lua bridge implementation")
        vm.execute(script_override if script_override is not None else script.read_text())
        globals_ = cast(Any, vm.globals())
        r = globals_["make_handle"](table(headers), table({PROVIDER: claims} if metadata is None else metadata))
        globals_["envoy_on_request"](r)
        return dict(r["h"]["values"].items()), r["status"], r["body"]

    def test_verified_cookie_is_forwarded_and_all_other_credentials_are_removed(self):
        headers, status, _ = self.bridge()
        self.assertIsNone(status)
        self.assertEqual(headers[TOKEN_HEADER.lower()], "synthetic.payload.signature")
        for name in ("cookie", "authorization", "x-webauth-user", "x-auth-request-email"):
            self.assertNotIn(name, headers)

    def test_presence_literal_group_and_profile_guards_fail_before_any_fallback(self):
        valid = {"iss": ISSUER, "aud": "grafana", "sub": "synthetic-owner-sub", "typ": "ID", "azp": "grafana",
                 "exp": 2000000000, "iat": 1900000000, "groups": ["/grafana-admins"]}
        cases = [{"exp": None}, {"exp": "2000000000"}, {"exp": False}, {"exp": float("nan")},
                 {"iat": None}, {"iat": "1900000000"}, {"iat": float("inf")},
                 {"iss": ISSUER + "/"}, {"aud": "argocd"}, {"aud": ["grafana", "other"]},
                 {"aud": {"owner": "grafana"}}, {"azp": "other"}, {"azp": None}, {"azp": []}, {"typ": "Bearer"},
                 {"sub": ""}, {"sub": False}, {"groups": "/grafana-admins"}, {"groups": []},
                 {"groups": ["/grafana-admins-extra"]}, {"groups": {"role": "/grafana-admins"}},
                 {"groups": ["/grafana-admins", 7]}, {"name": "must-not-rewrite-owner"},
                 {"email": "must-not-link@example.invalid"}, {"preferred_username": "must-not-rename"}]
        for override in cases:
            with self.subTest(override=override):
                headers, status, body = self.bridge({**valid, **override})
                self.assertEqual(status, "403")
                self.assertNotIn(TOKEN_HEADER.lower(), headers)
                self.assertNotIn("cookie", headers)
                self.assertNotIn("authorization", headers)
                self.assertEqual(body, "SSO authorization failed.")
        for md in ({}, {"wrong-provider": valid}, {PROVIDER: "not-a-payload"}):
            self.assertEqual(self.bridge(valid, metadata=md)[1], "403")

    def test_cookie_ambiguity_missing_and_compact_format_are_rejected(self):
        for cookie in ("grafana_session=old-cookie", "", COOKIE + "=not-a-jws",
                       COOKIE + "=a.b.c; " + COOKIE + "=d.e.f",
                       COOKIE + "=a.b.c," + COOKIE + "=d.e.f", COOKIE + '="a.b.c"'):
            with self.subTest(cookie=cookie):
                headers, status, body = self.bridge(header_overrides={"cookie": cookie})
                self.assertEqual(status, "403")
                self.assertNotIn(TOKEN_HEADER.lower(), headers)
                self.assertEqual(body, "SSO authorization failed.")

    def test_native_time_and_private_subject_checks_are_not_faked_in_lua(self):
        # Numeric dates intentionally pass presence; actual signature/time/owner checks
        # run in Envoy and Grafana, exercised by the pinned Go component suite.
        claims = {"iss": ISSUER, "aud": ["grafana"], "sub": "synthetic-other-sub", "typ": "ID",
                  "exp": 1, "iat": 1, "groups": ["/grafana-admins"], "azp": "grafana"}
        headers, status, _ = self.bridge(claims)
        self.assertIsNone(status)
        self.assertNotIn("cookie", headers)
        self.assertNotIn("authorization", headers)

    def test_controlled_mutation_proves_missing_iat_guard_is_observable(self):
        script = (CHART / "files/grafana-keycloak.lua").read_text()
        broken = script.replace("or not number(claims.iat)", "", 1)
        self.assertNotEqual(script, broken)
        claims = {"iss": ISSUER, "aud": "grafana", "sub": "synthetic-owner-sub", "typ": "ID", "azp": "grafana",
                  "exp": 2000000000, "groups": ["/grafana-admins"]}
        self.assertEqual(self.bridge(claims)[1], "403")
        self.assertIsNone(self.bridge(claims, script_override=broken)[1])

    def test_script_and_denials_do_not_expose_tokens_or_private_identity(self):
        script = (CHART / "files/grafana-keycloak.lua").read_text()
        self.assertNotRegex(script, r"require\s*\(|cjson|logInfo\s*\(|logWarn\s*\(|logErr\s*\(")
        _, status, body = self.bridge(header_overrides={"cookie": COOKIE + "=synthetic-private-marker"})
        self.assertEqual(status, "403")
        self.assertNotIn("synthetic-private-marker", body)


class GatewayTests(unittest.TestCase):
    def test_header_only_canary_preserves_normal_password_route_and_exact_callback(self):
        objs = objects("canary")
        self.assertIn(("SecurityPolicy", "grafana-keycloak"), objs)
        spec = objs["SecurityPolicy", "grafana-keycloak"]["spec"]
        self.assertEqual(spec["targetRefs"][0]["name"], "grafana-keycloak-canary")
        oidc = spec["oidc"]
        self.assertEqual(oidc["clientID"], "grafana")
        self.assertEqual(oidc["scopes"], ["openid", "groups"])
        self.assertEqual(oidc["redirectURL"], "https://grafana.kkamji.net/oauth2/keycloak-callback")
        self.assertFalse(oidc["disableTokenEncryption"])
        self.assertNotIn("forwardIDToken", oidc)
        self.assertNotIn("cookieDomain", oidc)
        jwt, = spec["jwt"]["providers"]
        self.assertEqual(jwt["name"], PROVIDER)
        self.assertEqual(jwt["extractFrom"], {"cookies": [COOKIE]})
        route = objs["HTTPRoute", "grafana-keycloak-canary"]["spec"]
        self.assertEqual(route["hostnames"], ["grafana.kkamji.net"])
        self.assertEqual(route["rules"][0]["matches"], [{"path": {"type": "PathPrefix", "value": "/"},
            "headers": [{"name": "X-KKamJi-SSO-Canary", "type": "Exact", "value": "grafana"}]}])
        self.assertFalse(any(f["type"] == "URLRewrite" for r in route["rules"] for f in r.get("filters", [])))
        policy_targets = [ref["name"] for (kind, _), d in objs.items() if kind == "SecurityPolicy"
                          for ref in d["spec"].get("targetRefs", [])]
        self.assertNotIn("grafana", policy_targets, "normal /login must remain outside OIDC in canary")
        normal = objs["HTTPRoute", "grafana"]["spec"]["rules"][-1]
        removed = {x.lower() for f in normal["filters"] for x in f["requestHeaderModifier"]["remove"]}
        self.assertIn(TOKEN_HEADER.lower(), removed)
        self.assertNotIn("cookie", removed)
        self.assertNotIn("authorization", removed)
        extension = objs["EnvoyExtensionPolicy", "grafana-keycloak-bridge"]["spec"]
        self.assertEqual(extension["targetRefs"][0]["name"], "grafana-keycloak-canary")
        self.assertEqual(extension["lua"][0]["inline"], (CHART / "files/grafana-keycloak.lua").read_text())

    def test_machine_route_is_separate_and_strips_cookie_and_identity_but_not_bearer(self):
        for mode in ("canary", "only"):
            objs = objects(mode)
            self.assertIn(("HTTPRoute", "grafana-machine-api"), objs)
            machine = objs["HTTPRoute", "grafana-machine-api"]["spec"]
            matches = machine["rules"][0]["matches"]
            self.assertEqual({m["path"]["value"] for m in matches}, {"/api", "/apis"})
            self.assertTrue(all(m["headers"] == [{"name": "Authorization", "type": "RegularExpression", "value": "^Bearer .+$"}] for m in matches))
            remove = {x.lower() for f in machine["rules"][0]["filters"] for x in f["requestHeaderModifier"]["remove"]}
            self.assertIn("cookie", remove)
            self.assertIn(TOKEN_HEADER.lower(), remove)
            self.assertIn("x-webauth-user", remove)
            self.assertNotIn("authorization", remove)
            for (kind, _), policy in objs.items():
                if kind in ("SecurityPolicy", "EnvoyExtensionPolicy"):
                    self.assertNotIn("grafana-machine-api", [r["name"] for r in policy["spec"].get("targetRefs", [])])

    def test_final_browser_never_forwards_cookie_or_authorization_and_gate_stays_explicit(self):
        objs = objects("only")
        self.assertEqual(objs["SecurityPolicy", "grafana-keycloak"]["spec"]["targetRefs"][0]["name"], "grafana")
        self.assertNotIn(("HTTPRoute", "grafana-keycloak-canary"), objs)
        rule = objs["HTTPRoute", "grafana"]["spec"]["rules"][-1]
        remove = {x.lower() for f in rule["filters"] if f["type"] == "RequestHeaderModifier"
                  for x in f["requestHeaderModifier"]["remove"]}
        self.assertTrue({"cookie", "authorization"} <= remove)
        self.assertNotIn(TOKEN_HEADER.lower(), remove, "do not remove Lua's validated token after injection")
        for gate in ("backendTLSReady", "grafana.dataPreservationReady", "grafana.accessLogsSafe"):
            self.assertNotEqual(render("canary", "--set", "keycloakSSO." + gate + "=false").returncode, 0)
        self.assertNotEqual(render("only", "--set", "keycloakSSO.grafana.cutoverApproved=false").returncode, 0)

    def pick_route(self, mode, path, headers):
        headers = {k.lower(): v for k, v in headers.items()}
        candidates = []
        for (kind, name), obj in objects(mode).items():
            if kind != "HTTPRoute" or obj["spec"].get("hostnames") != ["grafana.kkamji.net"]:
                continue
            for rule in obj["spec"]["rules"]:
                for match in rule["matches"]:
                    prefix = match["path"]["value"]
                    if not (path == prefix or prefix == "/" or path.startswith(prefix + "/")):
                        continue
                    accepted = True
                    for h in match.get("headers", []):
                        value = headers.get(h["name"].lower(), "")
                        if h["type"] == "Exact":
                            accepted &= value == h["value"]
                        else:
                            accepted &= re.fullmatch(h["value"], value) is not None
                    if accepted:
                        candidates.append((len(prefix), len(match.get("headers", [])), name, rule))
        if not candidates:
            raise AssertionError("no matching route")
        # Gateway API precedence: longest path, then most header matches.
        _, _, name, rule = max(candidates, key=lambda x: (x[0], x[1]))
        return name, rule

    def test_raw_duplicate_cookie_reject_precedes_oauth_normalization(self):
        bad = [COOKIE + "=a.b.c; " + COOKIE + "=d.e.f",
               "x=1; " + COOKIE + "=a.b.c; y=2; " + COOKIE + "=d.e.f; z=3",
               "  " + COOKIE + "=a.b.c;  " + COOKIE + "=a.b.c",
               COOKIE + "=a.b.c," + COOKIE + "=d.e.f"]
        for mode in ("canary", "only"):
            selector = {"X-KKamJi-SSO-Canary": "grafana"} if mode == "canary" else {}
            for raw in bad:
                with self.subTest(mode=mode, raw=raw):
                    self.assertEqual(self.pick_route(mode, "/", {**selector, "Cookie": raw})[0], "grafana-keycloak-cookie-reject")
            self.assertNotEqual(self.pick_route(mode, "/", {**selector, "Cookie": COOKIE + "=a.b.c; grafana_session=old"})[0], "grafana-keycloak-cookie-reject")
        self.assertEqual(self.pick_route("canary", "/login", {"Cookie": bad[0]})[0], "grafana")
        for (kind, _), policy in objects("only").items():
            if kind in ("SecurityPolicy", "EnvoyExtensionPolicy"):
                self.assertNotIn("grafana-keycloak-cookie-reject", [r["name"] for r in policy["spec"].get("targetRefs", [])])

    def test_old_cookie_plus_fake_bearer_cannot_become_owner_via_jwt_or_session(self):
        for mode in ("canary", "only"):
            route, rule = self.pick_route(mode, "/api/user", {"Authorization": "Bearer fake",
                "Cookie": "grafana_session=old-cookie; " + COOKIE + "=a.b.c",
                TOKEN_HEADER: "owner-token", "X-KKamJi-SSO-Canary": "grafana"})
            self.assertEqual(route, "grafana-machine-api")
            incoming = {"authorization": "Bearer fake", "cookie": "old-cookie", TOKEN_HEADER.lower(): "owner-token"}
            for f in rule["filters"]:
                for name in f["requestHeaderModifier"]["remove"]:
                    incoming.pop(name.lower(), None)
            self.assertEqual(incoming, {"authorization": "Bearer fake"})
            # Invalid native API token now has no JWT or session credential to fall back to.
            # Actual service-token validity remains Grafana's native API-key store decision.

    def test_ini_shadowing_and_partial_legacy_rollback_are_rejected(self):
        overrides = ["kube-prometheus-stack.grafana.env.GF_AUTH_JWT_USERNAME_CLAIM=sub",
                     "kube-prometheus-stack.grafana.env.GF_AUTH_PROXY_ENABLED=true",
                     "kube-prometheus-stack.grafana.envFromSecrets[0].name=bulk-env",
                     "keycloakSSO.grafana.mode=legacy"]
        for override in overrides:
            with self.subTest(override=override):
                self.assertNotEqual(render("canary", "--set-string", override).returncode, 0)

    def test_lua_header_mutation_keeps_canary_route_stable_until_router_finalization(self):
        headers, status, _ = LuaBridgeTests().bridge(header_overrides={"x-kkamji-sso-canary": "grafana"})
        self.assertIsNone(status)
        self.assertEqual(headers["x-kkamji-sso-canary"], "grafana")
        self.assertEqual(self.pick_route("canary", "/api/user", headers)[0], "grafana-keycloak-canary")
        # Controlled in-memory mutation demonstrates why selector removal in Lua is wrong.
        broken = dict(headers); broken.pop("x-kkamji-sso-canary")
        self.assertEqual(self.pick_route("canary", "/api/user", broken)[0], "grafana")
        canary = objects("canary")["HTTPRoute", "grafana-keycloak-canary"]
        self.assertEqual(canary["spec"]["rules"][0]["filters"][0]["requestHeaderModifier"]["remove"], ["X-KKamJi-SSO-Canary"])

    def test_public_basic_and_raw_cookie_denials_have_no_auth_or_lua_filter(self):
        objs = objects("only")
        for raw in ("Basic abc", "bAsIc abc", "BASIC abc"):
            self.assertEqual(self.pick_route("only", "/login", {"Authorization": raw})[0], "grafana-public-basic-deny")
            self.assertEqual(self.pick_route("only", "/", {"Authorization": raw,
                "Cookie": COOKIE + "=a.b.c; " + COOKIE + "=d.e.f"})[0], "grafana-keycloak-cookie-reject")
        for (kind, _), policy in objs.items():
            if kind in ("SecurityPolicy", "EnvoyExtensionPolicy"):
                targets = [r["name"] for r in policy["spec"].get("targetRefs", [])]
                self.assertNotIn("grafana-public-basic-deny", targets)
                self.assertNotIn("grafana-keycloak-cookie-reject", targets)

    def test_actual_pinned_envoy_schemas_reject_unknown_fields(self):
        import tarfile
        import jsonschema
        from test_keycloak_consumers import strict_schema
        schemas = {}
        with tarfile.open(ROOT / "charts/envoy-gateway/charts/gateway-helm-1.8.1.tgz") as vendor:
            for member in vendor.getmembers():
                if member.isfile() and any(member.name.endswith("gateway.envoyproxy.io_" + name + ".yaml")
                    for name in ("securitypolicies", "backends", "httproutefilters", "envoyextensionpolicies")):
                    stream = vendor.extractfile(member)
                    assert stream is not None
                    crd = yaml.safe_load(stream)
                    version = next(v for v in crd["spec"]["versions"] if v["name"] == "v1alpha1")
                    schemas[crd["spec"]["names"]["kind"]] = strict_schema(version["schema"]["openAPIV3Schema"]["properties"]["spec"])
        for mode in ("canary", "only"):
            for (kind, _), obj in objects(mode).items():
                if kind in schemas:
                    jsonschema.Draft7Validator(schemas[kind]).validate(obj["spec"])
        bad = copy.deepcopy(objects("canary")["EnvoyExtensionPolicy", "grafana-keycloak-bridge"]["spec"])
        bad["lua"][0]["runBeforeOIDC"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft7Validator(schemas["EnvoyExtensionPolicy"]).validate(bad)

    def test_readiness_acknowledgements_require_true_booleans_not_truthy_strings(self):
        for key in ("backendTLSReady", "grafana.dataPreservationReady", "grafana.accessLogsSafe"):
            with self.subTest(key=key):
                self.assertNotEqual(render("canary", "--set-string", "keycloakSSO." + key + "=false").returncode, 0)
        self.assertNotEqual(render("only", "--set-string", "keycloakSSO.grafana.cutoverApproved=false").returncode, 0)


if __name__ == "__main__":
    unittest.main()
