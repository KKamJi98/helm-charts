"""Offline tests for scoped public Keycloak HTTPRoute and persistent SSO cookie Lua."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM_BIN", "helm")
CHART = ROOT / "charts/keycloak-public-access"
MGMT_VALUES = ROOT / "charts/argo-applications/management_local_values.yaml"


def render(
    release="keycloak-public-access",
    namespace="keycloak",
    values_file=None,
    extra_args=(),
):
    cmd = [
        HELM,
        "template",
        release,
        str(CHART),
        "-n",
        namespace,
        "--kube-version",
        "1.36.1",
    ]
    if values_file is not None:
        cmd.extend(["-f", str(values_file)])
    cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


class PublicRouteContractTests(unittest.TestCase):
    def test_defaults_fail_closed_with_zero_objects(self):
        result = render()
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        self.assertEqual(docs, [])

    def test_local_values_render_scoped_http_route_and_persistent_sso_policy(self):
        result = render(values_file=CHART / "kkamji_local_values.yaml")
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        self.assertEqual(len(docs), 2)
        by_kind = {d["kind"]: d for d in docs}
        self.assertEqual(set(by_kind), {"HTTPRoute", "EnvoyExtensionPolicy"})

        route = by_kind["HTTPRoute"]
        self.assertEqual(route["apiVersion"], "gateway.networking.k8s.io/v1")
        self.assertEqual(
            route["metadata"], {"name": "keycloak-public", "namespace": "keycloak"}
        )
        self.assertEqual(
            route["spec"],
            {
                "hostnames": ["sso.kkamji.net"],
                "parentRefs": [
                    {
                        "group": "gateway.networking.k8s.io",
                        "kind": "Gateway",
                        "name": "kkamji",
                        "namespace": "envoy-gateway-system",
                        "sectionName": "https",
                    }
                ],
                "rules": [
                    {
                        "matches": [
                            {"path": {"type": "PathPrefix", "value": "/realms/kkamji"}},
                            {"path": {"type": "PathPrefix", "value": "/resources"}},
                        ],
                        "backendRefs": [
                            {
                                "group": "",
                                "kind": "Service",
                                "name": "keycloak-service",
                                "port": 8080,
                                "weight": 1,
                            }
                        ],
                    }
                ],
            },
        )
        paths = [
            m["path"]["value"] for r in route["spec"]["rules"] for m in r["matches"]
        ]
        self.assertEqual(paths, ["/realms/kkamji", "/resources"])
        for forbidden in ("/", "/admin", "/realms/master", "/health", "/metrics"):
            self.assertNotIn(forbidden, paths)

        policy = by_kind["EnvoyExtensionPolicy"]
        self.assertEqual(policy["apiVersion"], "gateway.envoyproxy.io/v1alpha1")
        self.assertEqual(
            policy["metadata"],
            {"name": "keycloak-public-persistent-sso", "namespace": "keycloak"},
        )
        self.assertEqual(
            policy["spec"]["targetRefs"],
            [
                {
                    "group": "gateway.networking.k8s.io",
                    "kind": "HTTPRoute",
                    "name": "keycloak-public",
                }
            ],
        )
        lua_items = policy["spec"]["lua"]
        self.assertEqual(len(lua_items), 1)
        self.assertEqual(lua_items[0]["type"], "Inline")
        inline = lua_items[0]["inline"]
        self.assertEqual(
            inline, (CHART / "files/persistent-sso-cookie.lua").read_text()
        )
        for forbidden_log in ("logInfo", "logWarn", "logErr", "logDebug", "print("):
            self.assertNotIn(forbidden_log, inline)

    def test_persistent_sso_cookie_lua_behavior(self):
        try:
            from lupa.luajit21 import LuaRuntime
        except ImportError:
            from lupa import LuaRuntime

        result = render(values_file=CHART / "kkamji_local_values.yaml")
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        policy = next(d for d in docs if d["kind"] == "EnvoyExtensionPolicy")
        lua_src = policy["spec"]["lua"][0]["inline"]

        vm = LuaRuntime()
        vm.execute(
            """
        function make_response_handle(input_cookies)
          local cookies = {}
          for i = 1, #input_cookies do cookies[i] = input_cookies[i] end
          local h = { cookies = cookies, mutated = false }
          function h:getNumValues(key)
            if string.lower(key) ~= "set-cookie" then return 0 end
            return #self.cookies
          end
          function h:getAtIndex(key, idx)
            if string.lower(key) ~= "set-cookie" then return nil end
            if idx < 0 or idx >= #self.cookies then return nil end
            return self.cookies[idx + 1]
          end
          function h:remove(key)
            if string.lower(key) == "set-cookie" then
              self.cookies = {}
              self.mutated = true
            end
          end
          function h:add(key, value)
            if string.lower(key) == "set-cookie" then
              self.cookies[#self.cookies + 1] = value
              self.mutated = true
            end
          end
          return { headers = function() return h end }, h
        end
        """
        )
        vm.execute(lua_src)
        make_handle = vm.globals().make_response_handle
        on_response = vm.globals().envoy_on_response

        def run_case(cookies):
            tbl = vm.table_from(cookies)
            handle, hdrs = make_handle(tbl)
            on_response(handle)
            out = [hdrs.cookies[i] for i in range(1, len(hdrs.cookies) + 1)]
            return bool(hdrs.mutated), out

        # 1) Google broker login: KEYCLOAK_IDENTITY & KEYCLOAK_SESSION lack Max-Age;
        #    transient cookies stay untouched and order is preserved.
        mutated, out = run_case(
            [
                "AUTH_SESSION_ID=abc.node1; Version=1; Path=/realms/kkamji/; SameSite=None; Secure; HttpOnly",
                "KEYCLOAK_IDENTITY=eyJheader.payload.sig; Version=1; Path=/realms/kkamji/; SameSite=None; Secure; HttpOnly",
                "KEYCLOAK_SESSION=kkamji/uid/sid; Version=1; Path=/realms/kkamji/; SameSite=None; Secure",
                "KC_RESTART=eyJrestart; Path=/realms/kkamji/; HttpOnly",
            ]
        )
        self.assertTrue(mutated)
        self.assertEqual(
            out,
            [
                "AUTH_SESSION_ID=abc.node1; Version=1; Path=/realms/kkamji/; SameSite=None; Secure; HttpOnly",
                "KEYCLOAK_IDENTITY=eyJheader.payload.sig; Version=1; Path=/realms/kkamji/; SameSite=None; Secure; HttpOnly; Max-Age=2592000",
                "KEYCLOAK_SESSION=kkamji/uid/sid; Version=1; Path=/realms/kkamji/; SameSite=None; Secure; Max-Age=2592000",
                "KC_RESTART=eyJrestart; Path=/realms/kkamji/; HttpOnly",
            ],
        )

        # 2) Logout cookies (empty value, Max-Age=0, Expires=1970) must NEVER be modified.
        logout_cookies = [
            "KEYCLOAK_IDENTITY=; Expires=Thu, 01-Jan-1970 00:00:10 GMT; Max-Age=0; Path=/realms/kkamji/; HttpOnly",
            "KEYCLOAK_SESSION=; Expires=Thu, 01-Jan-1970 00:00:10 GMT; Max-Age=0; Path=/realms/kkamji/",
        ]
        mutated, out = run_case(logout_cookies)
        self.assertFalse(mutated)
        self.assertEqual(out, logout_cookies)

        # 3) Native Remember Me cookie already having Max-Age must NOT get duplicate Max-Age.
        native_rm = [
            "KEYCLOAK_IDENTITY=eyJtok; Version=1; Path=/realms/kkamji/; Max-Age=2592000; Expires=Thu, 24-Dec-2026 00:00:00 GMT; SameSite=None; Secure; HttpOnly",
            "KEYCLOAK_SESSION=kkamji/uid/sid; Version=1; Path=/realms/kkamji/; Max-Age=604800; SameSite=None; Secure",
        ]
        mutated, out = run_case(native_rm)
        self.assertFalse(mutated)
        self.assertEqual(out, native_rm)

        # 4) Quoted empty value, wrong realm paths, and zero Set-Cookie responses stay untouched.
        untouched_cases = [
            ['KEYCLOAK_IDENTITY=""; Path=/realms/kkamji/; Secure; HttpOnly'],
            ["KEYCLOAK_IDENTITY=eyJtok; Path=/realms/master/; Secure; HttpOnly"],
            ["KEYCLOAK_IDENTITY=eyJtok; Path=/realms/kkamji2/; Secure; HttpOnly"],
            [],
        ]
        for cookies in untouched_cases:
            with self.subTest(cookies=cookies):
                mutated, out = run_case(cookies)
                self.assertFalse(mutated)
                self.assertEqual(out, cookies)

    def test_refuses_invalid_flags_extra_fields_and_wrong_identity(self):
        unsafe = [
            {"keycloakPublicRoute": {"enabled": "true"}},
            {"keycloakPublicRoute": {"enabled": 1}},
            {"keycloakPublicRoute": {"enabled": True, "hostname": "*.kkamji.net"}},
            {"keycloakPublicRoute": {"enabled": True}, "extra": True},
        ]
        for payload in unsafe:
            for skip_schema in (False, True):
                with self.subTest(payload=payload, skip_schema=skip_schema):
                    with tempfile.TemporaryDirectory() as tmp:
                        vf = Path(tmp) / "bad.yaml"
                        vf.write_text(yaml.safe_dump(payload))
                        extra = ("--skip-schema-validation",) if skip_schema else ()
                        res = render(values_file=vf, extra_args=extra)
                        self.assertNotEqual(res.returncode, 0)
        for release, ns in [
            ("other", "keycloak"),
            ("keycloak-public-access", "default"),
        ]:
            with self.subTest(release=release, ns=ns):
                res = render(
                    release=release,
                    namespace=ns,
                    values_file=CHART / "kkamji_local_values.yaml",
                )
                self.assertNotEqual(res.returncode, 0)
                self.assertIn("exact namespace/release identity required", res.stderr)

    def test_management_root_wires_keycloak_public_access_and_lints(self):
        values = yaml.safe_load(MGMT_VALUES.read_text())
        app = values["applications"].get("keycloak-public-access")
        self.assertEqual(
            app,
            {
                "enabled": True,
                "name": "keycloak-public-access",
                "project": "management",
                "destination": {"namespace": "keycloak"},
                "source": {
                    "repoURL": "https://github.com/KKamJi98/helm-charts.git",
                    "targetRevision": "main",
                    "path": "charts/keycloak-public-access",
                    "helm": {
                        "releaseName": "keycloak-public-access",
                        "valueFiles": ["kkamji_local_values.yaml"],
                    },
                },
            },
        )
        lint = subprocess.run(
            [
                HELM,
                "lint",
                "--strict",
                str(CHART),
                "-f",
                str(CHART / "kkamji_local_values.yaml"),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)


if __name__ == "__main__":
    unittest.main()
