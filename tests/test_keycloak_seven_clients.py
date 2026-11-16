"""Disabled source contract only. No IdP, DB, credential or HTTP calls."""
import copy
import hashlib
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'examples/keycloak-preparation/consumer-contract/seven-clients.yaml.inactive'
EXPECTED = {
    'kkamji-platform': ('platform', '/api/auth/oidc/callback', []),
    'argocd': ('argocd', '/auth/callback', ['profile', 'groups']),
    'grafana': ('grafana', '/oauth2/keycloak-callback', ['groups']),
    'hindsight-ui': ('hindsight', '/oauth2/keycloak-callback', ['profile', 'groups']),
    'hubble': ('hubble', '/oauth2/keycloak-callback', ['profile', 'groups']),
    'prometheus': ('prometheus', '/oauth2/keycloak-callback', ['profile', 'groups']),
    'alertmanager': ('alertmanager', '/oauth2/keycloak-callback', ['profile', 'groups']),
}


def assert_clients(case, contract):
    case.assertEqual(contract['keycloakVersion'], '26.8.2')
    case.assertEqual(contract['issuer'], 'https://sso.kkamji.net/realms/kkamji')
    case.assertIs(contract['runtimeAccepted'], False)
    case.assertIs(contract['dataMigrationAccepted'], False)
    realm = contract['realm']
    case.assertEqual(realm['realm'], 'kkamji')
    for key in ('enabled', 'registrationAllowed', 'resetPasswordAllowed', 'rememberMe'):
        case.assertIs(realm[key], False)
    case.assertEqual(realm['identityProviders'], [])
    for key in ('users', 'defaultGroups', 'defaultRoles', 'authenticationFlows', 'browserFlow'):
        case.assertNotIn(key, realm.keys())
    case.assertEqual(realm['webAuthnPolicyUserVerificationRequirement'], 'required')
    case.assertEqual(realm['webAuthnPolicyRpId'], 'sso.kkamji.net')
    case.assertIs(realm['webAuthnPolicyPasswordlessPasskeysEnabled'], False)
    clients = realm['clients']
    case.assertEqual(len(clients), 7)
    case.assertEqual({c['clientId'] for c in clients}, set(EXPECTED))
    for client in clients:
        cid = client['clientId']
        host, callback, optional = EXPECTED[cid]
        case.assertEqual(client['protocol'], 'openid-connect')
        case.assertEqual(client['clientAuthenticatorType'], 'client-secret')
        case.assertIs(client['standardFlowEnabled'], True)
        for key in ('enabled', 'publicClient', 'bearerOnly', 'implicitFlowEnabled',
                    'directAccessGrantsEnabled', 'serviceAccountsEnabled', 'fullScopeAllowed'):
            case.assertIs(client[key], False)
        case.assertEqual(client['redirectUris'], ['https://' + host + '.kkamji.net' + callback])
        case.assertEqual(client['webOrigins'], ['https://' + host + '.kkamji.net'])
        case.assertEqual(client['defaultClientScopes'], [])
        case.assertEqual(client['optionalClientScopes'], optional)
        case.assertEqual(client['authenticationFlowBindingOverrides'], {})
        case.assertEqual(client['attributes']['pkce.code.challenge.method'], 'S256')
        case.assertEqual(client['attributes']['id.token.signed.response.alg'], 'RS256')
        for key in ('oauth2.device.authorization.grant.enabled', 'oidc.ciba.grant.enabled',
                    'standard.token.exchange.enabled', 'oauth2.jwt.authorization.grant.enabled', 'external.token.enabled'):
            case.assertEqual(client['attributes'][key], 'false')
        for key in ('secret', 'registrationAccessToken', 'protocolMappers', 'defaultRoles'):
            case.assertNotIn(key, client.keys())


class SevenClientContractTests(unittest.TestCase):
    def load(self):
        self.assertTrue(PATH.is_file(), 'disabled seven-client source contract is required')
        return yaml.safe_load(PATH.read_text())

    def test_seven_disabled_confidential_code_s256_clients_exact_scopes(self):
        assert_clients(self, self.load())

    def test_optional_full_path_groups_are_signed_id_token_only(self):
        realm = self.load()['realm']
        self.assertEqual({g['name'] for g in realm.get('groups', [])},
                         {'argocd-admins', 'grafana-admins', 'homelab-admins'})
        self.assertEqual(realm.get('defaultDefaultClientScopes'), [])
        self.assertEqual(realm.get('defaultOptionalClientScopes'), [])
        self.assertEqual(realm.get('defaultSignatureAlgorithm'), 'RS256')
        scopes = realm.get('clientScopes', [])
        self.assertEqual(len(scopes), 1, 'exactly one explicit groups scope required')
        scope, = scopes
        self.assertEqual(scope['name'], 'groups')
        self.assertEqual(scope['protocol'], 'openid-connect')
        mapper, = scope['protocolMappers']
        self.assertEqual(mapper['protocol'], 'openid-connect')
        self.assertEqual(mapper['protocolMapper'], 'oidc-group-membership-mapper')
        self.assertEqual(mapper['config'], {'claim.name': 'groups', 'full.path': 'true',
            'id.token.claim': 'true', 'access.token.claim': 'false', 'userinfo.token.claim': 'false',
            'introspection.token.claim': 'false', 'lightweight.claim': 'false'})



    def test_secure_refs_and_supported_lifecycle_do_not_embed_private_values(self):
        contract = self.load()
        refs = contract.get('clientSecretRefs', {})
        self.assertEqual(set(refs), set(EXPECTED), 'all seven client secret references required')
        namespaces = {'argocd': 'argocd', 'grafana': 'monitoring', 'hindsight-ui': 'hindsight',
                      'hubble': 'kube-system', 'prometheus': 'monitoring', 'alertmanager': 'monitoring',
                      'kkamji-platform': 'keycloak'}
        for cid, namespace in namespaces.items():
            ref = refs[cid]
            self.assertEqual(ref['remoteRef'], {'key': '/kkamji/keycloak/clients/' + cid, 'property': 'client_secret'})
            self.assertEqual(ref['secretStoreRef'], {'name': 'parameter-store', 'kind': 'ClusterSecretStore'})
            self.assertEqual(ref['existingESORef'], {'namespace': namespace,
                'name': 'keycloak-oidc-client' if cid == 'kkamji-platform' else cid + '-keycloak-oidc',
                'secretKey': 'client-secret'})
            self.assertEqual(ref['creationPolicy'], 'Orphan')
            self.assertEqual(ref['deletionPolicy'], 'Retain')
            self.assertEqual(set(ref), {'remoteRef', 'secretStoreRef', 'existingESORef', 'creationPolicy', 'deletionPolicy'})
        self.assertEqual(contract['grafanaIdentityRef'], {'namespace': 'monitoring',
            'name': 'grafana-keycloak-identity', 'remoteKey': '/kkamji/keycloak/consumers/grafana',
            'properties': ['username_attribute_path', 'expect_claims']})
        self.assertEqual(contract['lifecycle']['historicalCreateOnlySeed'], '../realm-import.yaml.inactive')
        self.assertEqual(contract['lifecycle']['existingRealmUpdate'], 'supported Admin API or console with exact before/after readback')
        self.assertIs(contract['lifecycle']['realmImportReapplyUpdatesExistingRealm'], False)
        self.assertIs(contract['lifecycle']['esoRefreshRotatesIdpClient'], False)
        self.assertEqual(contract['ownerInputStatus'], 'login ID missing; parent asks human, private iss/sub and legacy identity readback pending')

    def test_unsafe_contract_mutations_are_observable(self):
        base = self.load()
        for field, value in (('enabled', True), ('publicClient', True), ('redirectUris', ['https://*.kkamji.net/*']),
                             ('defaultClientScopes', ['profile', 'email']), ('optionalClientScopes', ['email'])):
            with self.subTest(field=field):
                mutation = copy.deepcopy(base)
                client = next(c for c in mutation['realm']['clients'] if c['clientId'] == 'grafana')
                client[field] = value
                with self.assertRaises(AssertionError):
                    assert_clients(self, mutation)

    def test_realm_fields_match_pinned_26_8_2_vendor_schema(self):
        import jsonschema
        from test_keycloak_consumers import strict_schema
        crd = yaml.safe_load((ROOT / 'charts/keycloak-operator/crds/keycloakrealmimports.k8s.keycloak.org-v1.yml').read_text())
        version = next(v for v in crd['spec']['versions'] if v['name'] == 'v2beta1')
        schema = strict_schema(version['schema']['openAPIV3Schema']['properties']['spec']['properties']['realm'])
        validator = jsonschema.Draft7Validator(schema)
        self.assertFalse(list(validator.iter_errors(self.load()['realm'])), 'pinned realm schema rejected source contract')
        broken = copy.deepcopy(self.load()['realm'])
        broken['inventedOwnerReady'] = True
        self.assertTrue(list(validator.iter_errors(broken)), 'unknown realm field must be refused')

    def test_historical_one_client_seed_bytes_are_preserved(self):
        seed = ROOT / 'examples/keycloak-preparation/realm-import.yaml.inactive'
        self.assertEqual(hashlib.sha256(seed.read_bytes()).hexdigest(),
                         '7f53365c4a2709fa299c2bbf84b9f481979bf04bd27178651a6be65122752561')


if __name__ == '__main__':
    unittest.main()
