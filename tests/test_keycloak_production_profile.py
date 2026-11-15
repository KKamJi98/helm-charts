"""Offline production activation contract. No cloud/cluster/credential access.

Use verified HELM_BIN=Helm 4.2.1 and TMPDIR=owned private scratch. Existing
PyYAML/jsonschema only. Schema checks and local models are not admission,
controller execution, effective authorization, backup or restore acceptance.
"""
import copy
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import jsonschema
import yaml

import test_keycloak_preparation as preparation


BACKUP = {
    "barmanObjectStore": {
        "destinationPath": "s3://kkamji-keycloak-pg-backup/keycloak",
        "s3Credentials": {
            "accessKeyId": {"name": "keycloak-backup-s3", "key": "ACCESS_KEY_ID"},
            "secretAccessKey": {"name": "keycloak-backup-s3", "key": "ACCESS_SECRET_KEY"},
            "region": {"name": "keycloak-backup-s3", "key": "AWS_REGION"},
        },
        "data": {"compression": "gzip", "encryption": "AES256"},
        "wal": {"compression": "gzip", "encryption": "AES256"},
    },
    "retentionPolicy": "30d",
}
PRODUCTION = {
    "preparationProfile": "keycloak-26.8.2-production",
    "productionPhase": "database",
    "publicCaProjection": {"enabled": True},
    "database": {"backup": BACKUP},
}
# Derived from the v1 CRD at the existing pinned CNPG 1.30 commit:
# ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf/config/crd/bases/
# postgresql.cnpg.io_scheduledbackups.yaml, source SHA256:
SCHEDULED_CRD_SHA = "4613bd236e1087f499e6f01a98740998d28e025a074ccac3db9b4a3911c1e768"
SCHEDULED_SCHEMA_SHA = "2ae1c3e29f38e6c1e6dfe6936d37648247fb78b1f308e0cb9bd06b2443787233"


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys instead of silently accepting the last one."""


def unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise AssertionError("Duplicate YAML key: " + str(key))
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def documents(text):
    return [obj for obj in yaml.load_all(text, Loader=UniqueLoader) if obj]


def command(override=None, phase="database", skip_schema=False, namespace="keycloak", release="keycloak"):
    # Optional path is only for an isolated negative-test mutant, never a live chart.
    chart = Path(os.environ.get("KEYCLOAK_PRODUCTION_TEST_CHART", str(preparation.APP)))
    args = [preparation.HELM, "template", release, str(chart), "-n", namespace,
            "-f", str(chart / "kkamji_local_values.yaml"), "-f", str(chart / "production-values.yaml"),
            "--include-crds", "--skip-tests", "--kube-version", "1.36.1"]
    if skip_schema:
        args += ["--skip-schema-validation"]
    if override is None:
        return subprocess.run(args + ["--set", "productionPhase=" + phase], capture_output=True, text=True)
    with tempfile.TemporaryDirectory(prefix="keycloak-production-negative-") as tmp:
        path = Path(tmp) / "override.json"
        path.write_text(json.dumps({"productionPhase": phase, **override}))
        return subprocess.run(args + ["-f", str(path)], capture_output=True, text=True)


class KeycloakProductionProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not preparation.HELM:
            raise AssertionError("Set HELM_BIN to verified Helm 4.2.1")
        version = subprocess.run([preparation.HELM, "version", "--short"],
                                 capture_output=True, text=True, check=True).stdout.strip()
        if version != "v4.2.1+gd591a19":
            raise AssertionError("Expected v4.2.1+gd591a19")
        cls.schema = json.loads((preparation.APP / "values.schema.json").read_text())

    def render(self, phase="database"):
        result = command(phase=phase)
        self.assertEqual(result.returncode, 0, result.stderr)
        return documents(result.stdout)

    def test_database_tolerations_are_omitted_for_podspec_snapshot_stability(self):
        for phase in ("database", "application"):
            with self.subTest(phase=phase):
                cluster = next(obj for obj in self.render(phase) if obj["kind"] == "Cluster")
                self.assertNotIn("tolerations", cluster["spec"]["affinity"])

    def test_production_database_phase_declares_backup_before_app(self):
        result = preparation.KeycloakPreparationTests.command(preparation.APP, override=PRODUCTION)
        self.assertEqual(result.returncode, 0, result.stderr)
        objects = documents(result.stdout)
        by = {preparation.identity(obj): obj for obj in objects}
        self.assertNotIn(("Keycloak", "keycloak"), by)
        self.assertEqual(by[("Cluster", "keycloak-db")]["spec"]["backup"], BACKUP)
        self.assertIn(("ScheduledBackup", "keycloak-db-backup"), by)
        self.assertEqual(objects, self.render())

    def test_production_overlay_and_internal_profile_are_exact_and_defaults_untouched(self):
        overlay = yaml.load((preparation.APP / "production-values.yaml").read_text(), Loader=UniqueLoader)
        self.assertEqual(overlay, PRODUCTION)
        self.assertEqual(overlay, yaml.load((preparation.APP / "files/production-profile.yaml").read_text(), Loader=UniqueLoader))
        for path in ("values.yaml", "kkamji_local_values.yaml", "files/preparation-profile.yaml"):
            self.assertEqual(hashlib.sha256((preparation.APP / path).read_bytes()).hexdigest(),
                             "65ae8b1102219f6e391882fef3a286486700b044ad06e0291fb47f5596bff4f5")
        for override, expected in ((None, 8), ({"publicCaProjection": {"enabled": True}}, 15)):
            result = preparation.KeycloakPreparationTests.command(preparation.APP, override=override)
            self.assertEqual(result.returncode, 0, result.stderr)
            objs = documents(result.stdout)
            self.assertEqual(len(objs), expected)
            self.assertFalse([o for o in objs if o["kind"] == "ScheduledBackup"
                              or o["metadata"]["name"] == "keycloak-backup-s3"])
            self.assertNotIn("backup", next(o for o in objs if o["kind"] == "Cluster")["spec"])

    def test_phases_object_inventory_and_existing_security_configuration(self):
        result = preparation.KeycloakPreparationTests.command(
            preparation.APP, override={"publicCaProjection": {"enabled": True}})
        self.assertEqual(result.returncode, 0, result.stderr)
        baseline = {preparation.identity(o): o for o in documents(result.stdout)}
        db_objects = self.render()
        app_objects = self.render("application")
        db_by = {preparation.identity(o): o for o in db_objects}
        app_by = {preparation.identity(o): o for o in app_objects}
        self.assertEqual(len(db_objects), 16)
        self.assertEqual(len(app_objects), 17)
        self.assertEqual(len(db_by), len(db_objects))
        self.assertEqual(len(app_by), len(app_objects))
        self.assertEqual(set(app_by) - set(db_by), {("Keycloak", "keycloak")})
        self.assertEqual({k: app_by[k] for k in db_by}, db_by)
        for key, obj in baseline.items():
            if key[0] not in ("Keycloak", "Cluster"):
                self.assertEqual(app_by[key], obj)
        app = app_by[("Keycloak", "keycloak")]
        self.assertEqual(app["spec"], baseline[("Keycloak", "keycloak")]["spec"])
        self.assertEqual(app["metadata"]["annotations"], {"argocd.argoproj.io/sync-wave": "1"})
        db = copy.deepcopy(app_by[("Cluster", "keycloak-db")])
        self.assertEqual(db["spec"].pop("backup"), BACKUP)
        self.assertEqual(db, baseline[("Cluster", "keycloak-db")])
        for obj in app_objects:
            self.assertEqual(obj["metadata"]["namespace"], "keycloak")
            self.assertNotIn("local-only", json.dumps(obj))
        self.assertFalse({"Namespace", "Application", "HTTPRoute", "Ingress", "Secret", "CronJob",
                          "Job", "KeycloakRealmImport", "KeycloakOIDCClient", "KeycloakSAMLClient"}
                         & {o["kind"] for o in app_objects})
        self.assertFalse([o for o in app_objects if o["kind"] == "NetworkPolicy"
                          and "Egress" in o["spec"]["policyTypes"]])

    def test_backup_external_secret_exact_properties_and_public_region_merge(self):
        by = {preparation.identity(o): o for o in self.render()}
        obj = by[("ExternalSecret", "keycloak-backup-s3")]
        self.assertEqual(obj["metadata"]["annotations"], {"argocd.argoproj.io/sync-wave": "-1"})
        self.assertEqual(obj["spec"], {
            "refreshPolicy": "Periodic", "refreshInterval": "1h",
            "secretStoreRef": {"name": "parameter-store", "kind": "ClusterSecretStore"},
            "target": {"name": "keycloak-backup-s3", "creationPolicy": "Orphan", "deletionPolicy": "Retain",
                       "template": {"engineVersion": "v2", "mergePolicy": "Merge", "type": "Opaque",
                                    "data": {"AWS_REGION": "ap-northeast-2"}}},
            "data": [{"secretKey": key, "remoteRef": {
                "key": "/kkamji/keycloak/backup-s3", "property": prop, "conversionStrategy": "Default",
                "decodingStrategy": "None", "metadataPolicy": "None"}}
                for key, prop in [("ACCESS_KEY_ID", "access_key_id"), ("ACCESS_SECRET_KEY", "secret_access_key")]],
        })
        spec = obj["spec"]
        target_keys = [item["secretKey"] for item in spec["data"]] + list(spec["target"]["template"]["data"])
        self.assertEqual(len(target_keys), len(set(target_keys)))
        self.assertEqual(set(target_keys), {"ACCESS_KEY_ID", "ACCESS_SECRET_KEY", "AWS_REGION"})
        # Merge policy above retains provider data when adding the static region;
        # it is template mergePolicy, NOT target creationPolicy=Merge.
        self.assertNotIn("dataFrom", spec)
        creds = by[("Cluster", "keycloak-db")]["spec"]["backup"]["barmanObjectStore"]["s3Credentials"]
        self.assertEqual({ref["key"] for ref in creds.values()}, set(target_keys))
        self.assertTrue(all(ref["name"] == "keycloak-backup-s3" for ref in creds.values()))

    def test_daily_scheduled_backup_and_default_catalog_identity(self):
        by = {preparation.identity(o): o for o in self.render()}
        self.assertEqual(by[("ScheduledBackup", "keycloak-db-backup")]["spec"], {
            "schedule": "0 0 18 * * *", "backupOwnerReference": "cluster",
            "cluster": {"name": "keycloak-db"}, "method": "barmanObjectStore",
            "immediate": False, "suspend": False,
        })
        barman = by[("Cluster", "keycloak-db")]["spec"]["backup"]["barmanObjectStore"]
        self.assertNotIn("serverName", barman)
        self.assertNotIn("endpointURL", barman)
        kst = datetime(2026, 11, 16, 18, 0, 0, tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Seoul"))
        self.assertEqual((kst.day, kst.hour, kst.minute), (17, 3, 0))

    def test_pinned_cnpg_eso_and_scheduled_backup_schemas_and_unknown_fields(self):
        schema_file = preparation.ROOT / "tests/fixtures/keycloak-idp/cnpg-1.30-scheduledbackup.schema.json"
        self.assertEqual(hashlib.sha256(schema_file.read_bytes()).hexdigest(), SCHEDULED_SCHEMA_SHA)
        cnpg_path = preparation.EXAMPLES / "schemas/cnpg-1.30-cluster.schema.json"
        self.assertEqual(hashlib.sha256(cnpg_path.read_bytes()).hexdigest(),
                         "44ee1d0632632a5f3351de37114e35db92fc2b4ff07572546085dd578f6466cb")
        archive = preparation.ROOT / "charts/external-secrets/charts/external-secrets-2.4.1.tgz"
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),
                         "d432db5dd4935cc8032f6fbc1c3f33b4baaa08db2be76de41e6cf3ea651fe574")
        result = subprocess.run([preparation.HELM, "template", "eso-schema", str(archive),
                                 "--show-only", "templates/crds/externalsecret.yaml"],
                                capture_output=True, text=True, check=True)
        schemas = {"Cluster": json.loads(cnpg_path.read_text()),
                   "ScheduledBackup": json.loads(schema_file.read_text()),
                   "ExternalSecret": preparation.crd_schema(yaml.safe_load(result.stdout), "v1"),
                   "Keycloak": preparation.crd_schema(yaml.safe_load((preparation.OPERATOR /
                       "crds/keycloaks.k8s.keycloak.org-v1.yml").read_text()), "v2beta1")}
        for obj in self.render("application"):
            if obj["kind"] in schemas:
                preparation.validate_document(schemas[obj["kind"]], obj)
        by = {preparation.identity(o): o for o in self.render()}
        cases = [
            ("Cluster", "keycloak-db", ("spec", "backup", "barmanObjectStore", "s3Credentials", "region"), "ap-northeast-2"),
            ("Cluster", "keycloak-db", ("spec", "backup", "barmanObjectStore", "s3Credentials", "regoin"), {}),
            ("Cluster", "keycloak-db", ("spec", "backup", "barmanObjectStore", "data", "encryption"), "none"),
            ("ScheduledBackup", "keycloak-db-backup", ("spec", "timeZone"), "Asia/Seoul"),
            ("ScheduledBackup", "keycloak-db-backup", ("spec", "backupOwnerReference"), "Owner"),
            ("ScheduledBackup", "keycloak-db-backup", ("spec", "immediate"), "false"),
            ("ExternalSecret", "keycloak-backup-s3", ("spec", "target", "template", "mergePolicy"), "MergeAll"),
            ("ExternalSecret", "keycloak-backup-s3", ("spec", "target", "template", "dataTypo"), {}),
        ]
        for kind, name, path, value in cases:
            with self.subTest(kind=kind, path=path):
                invalid = copy.deepcopy(by[(kind, name)])
                cursor = invalid
                for part in path[:-1]:
                    cursor = cursor[part]
                cursor[path[-1]] = value
                with self.assertRaises(jsonschema.ValidationError):
                    preparation.validate_document(schemas[kind], invalid)

    def test_production_refuses_missing_ca_backup_and_phase_with_or_without_schema(self):
        for override in ({"publicCaProjection": {"enabled": False}},
                         {"database": {"backup": None}},
                         {"productionPhase": None}, {"productionPhase": "startup"}):
            for skip in (False, True):
                with self.subTest(override=override, skip_schema=skip):
                    result = command(override, skip_schema=skip)
                    self.assertNotEqual(result.returncode, 0)
                    if skip:
                        self.assertIn("immutable supported-field profile mismatch", result.stderr)

    def test_production_refuses_backup_or_security_drift_without_silent_discard(self):
        cases = [
            {"database": {"backup": {"retentionPolicy": "37d"}}},
            {"database": {"backup": {"barmanObjectStore": {"destinationPath": "s3://other/keycloak"}}}},
            {"database": {"backup": {"barmanObjectStore": {"serverName": "other"}}}},
            {"database": {"backup": {"barmanObjectStore": {"endpointURL": "http://example.invalid"}}}},
            {"database": {"backup": {"barmanObjectStore": {"s3Credentials": {"region": "ap-northeast-2"}}}}},
            {"database": {"backup": {"barmanObjectStore": {"s3Credentials": {"region": None}}}}},
            {"database": {"backup": {"barmanObjectStore": {"data": {"encryption": None}}}}},
            {"database": {"backup": {"barmanObjectStore": {"wal": {"compression": "none"}}}}},
            {"database": {"backup": {"plugins": [{"name": "new-controller"}]}}},
            {"backup": {"enabled": True}},
            {"productionPhase": "application", "publicCaProjection": {"enabled": False}},
            {"preparationProfile": "keycloak-26.8.2-local-only"},
            {"preparationProfile": "keycloak-26.8.2-anything"},
            {"keycloak": {"instances": 1}},
            {"keycloak": {"automountServiceAccountToken": True}},
            {"keycloak": {"additionalOptions": [{"name": "db-tls-mode", "value": "disabled"}]}},
            {"database": {"affinity": {"nodeAffinity": None}}},
            {"productionPhase": "application", "keycloak": {"image": "quay.io/keycloak/keycloak:26.8.2"}},
        ]
        for override in cases:
            for skip in (False, True):
                with self.subTest(override=override, skip_schema=skip):
                    result = command(override, skip_schema=skip)
                    self.assertNotEqual(result.returncode, 0)
                    if skip:
                        self.assertIn("immutable supported-field profile mismatch", result.stderr)
        for namespace, release in (("default", "keycloak"), ("keycloak", "other")):
            result = command(namespace=namespace, release=release)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exact namespace/release identity required", result.stderr)

    def test_values_schema_enforces_profile_pairs_without_template_guard(self):
        values = yaml.safe_load((preparation.APP / "values.yaml").read_text())
        production = copy.deepcopy(values)
        production.update({key: value for key, value in PRODUCTION.items() if key != "database"})
        production["database"]["backup"] = copy.deepcopy(BACKUP)
        jsonschema.Draft7Validator.check_schema(self.schema)
        for candidate in (values, production, {**production, "productionPhase": "application"}):
            jsonschema.validate(candidate, self.schema)
        invalids = []
        for field in ("productionPhase", "database", "publicCaProjection"):
            invalid = copy.deepcopy(production)
            invalid.pop(field)
            invalids.append(invalid)
        invalids += [{**production, "publicCaProjection": {"enabled": False}},
                     {**values, "productionPhase": "database"}]
        invalid = copy.deepcopy(production)
        invalid["database"].pop("backup")
        invalids.append(invalid)
        invalid = copy.deepcopy(production)
        invalid["database"]["backup"]["retentionPolciy"] = "30d"
        invalids.append(invalid)
        for invalid in invalids:
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(invalid, self.schema)

    def test_helm_strict_lint_both_production_phases(self):
        for phase in ("database", "application"):
            result = subprocess.run([preparation.HELM, "lint", str(preparation.APP), "--strict",
                                     "-f", str(preparation.APP / "kkamji_local_values.yaml"),
                                     "-f", str(preparation.APP / "production-values.yaml"),
                                     "--set", "productionPhase=" + phase], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
