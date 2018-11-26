'''
Support for loading secret tokens from HashiCorp's Vault server.
'''

import os

import hvac
import six
import yaml


def import_vault_secrets(tokens, vault_auth_conf, vault_map_path):
    '''
    Import all relevant secrets from Vault.

    Parses Vault/Django tokens map and updates `tokens` dict with values retrieved from Vault.
    The tokens map has format:

        ENV_TOKEN_NAME: VAULT_TOKEN_PATH
        or
        ENV_TOKEN_NAME:
            path: VAULT_TOKEN_PATH
            tokens: TOKEN_LIST_TO_LOAD

    Supports 2 types of token references:
        - simple tokens: map entry points directly to an atomic value
        - dict tokens: map entry points to a Vault path containing several tokens that
          will be imported as a dict

    Dict tokens must have 2 keys: 
        - `path` pointing to a Vault path containing tokens;
        - `tokens` specifying the list of tokens to be loaded.

    :param tokens: original tokens dict to be updated
    :type tokens: dict
    :param vault_auth_conf: path to Vault authentication file
    :param vault_map_path: path to Vault map file
    :returns: updated tokens dict
    :rtype: dict
    '''
    # read vault config and create a client
    with open(vault_auth_conf, 'r') as vault_conf_file:
        conf = yaml.load(vault_conf_file)
        vault_client = hvac.Client(url=conf['url'], verify=conf['ssl_verify'])
        vault_client.auth_approle(conf['role_id'], conf['secret_id'], 'approle', 'approle')
        if not vault_client.is_authenticated():
            raise Exception('Vault Authentication failed')
    # read vault secrets to env tokens map and load mapped secrets from vault into tokens
    with open(vault_map_path, 'r') as vault_map_file:
        for (env_key, secret_loc) in yaml.load(vault_map_file).iteritems():
            if secret_loc:
                if isinstance(secret_loc, six.string_types):
                    # simple secret: path points directly to a key
                    secret = vault_client.read(os.path.dirname(secret_loc))
                    if not secret:
                        continue
                    key = os.path.basename(secret_loc)
                    tokens[env_key] = secret['data'][key]
                elif isinstance(secret_loc, dict):
                    keys_to_load = secret_loc.get('tokens')
                    secret_path = secret_loc['path']
                    # composite secret: will be read as a dict of all Vault key-value pairs at `secret_path`
                    secret = {}
                    dct = vault_client.read(secret_path)
                    if dct and 'data' in dct:
                        data = dct['data']
                        for key in keys_to_load:
                            secret[key] = data[key]
                        # initialize the key if it does not exist
                        tokens[env_key] = tokens.get(env_key, {})
                        tokens[env_key].update(secret)
                else:
                    # use print() here as logging may not yet be initialized
                    print('ERROR:config:vault: Unrecognized secret path: %s' % secret_path)

    return tokens
