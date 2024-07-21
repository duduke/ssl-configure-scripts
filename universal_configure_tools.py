#!/usr/bin/env python3
import os
import subprocess
import requests
import platform
import shutil

# Determine if the OS is Windows
is_windows = platform.system() == "Windows"

def get_shell():
    if is_windows:
        return None  # Windows CMD does not need a shell profile file
    else:
        my_shell = os.getenv('SHELL')
        print(f'Shell used is {my_shell}')
        if 'bash' in my_shell:
            return os.path.expanduser('~/.bash_profile')
        else:
            return os.path.expanduser('~/.zshenv')

shell = get_shell()

def get_input(prompt, default):
    user_input = input(f'{prompt} [{default}]: ')
    return user_input if user_input else default

cert_name = get_input('Please provide certificate bundle name', 'netskope-cert-bundle.pem')
cert_dir = get_input('Please provide certificate bundle location', '~/netskope')
cert_dir = os.path.expanduser(cert_dir)

if not os.path.isdir(cert_dir):
    print(f'{cert_dir} does not exist.')
    print(f'creating {cert_dir}')
    os.makedirs(cert_dir, exist_ok=True)

tenant_name = input('Please provide full tenant name (ex: mytenant.eu.goskope.com): ')
org_key = input('Please provide tenant orgkey: ')

status_code = requests.get(f'https://{tenant_name}/locallogin').status_code

if status_code !=200:
    print('Tenant Unreachable')
    exit(1)
else:
    print('Tenant Reachable')

def command_exists(command):
    return subprocess.call(f'command -v {command}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0 if not is_windows else shutil.which(command) is not None

def create_cert_bundle():
    print('Creating cert bundle')
    urls = [
        f'https://addon-{tenant_name}/config/ca/cert?orgkey={org_key}',
        f'https://addon-{tenant_name}/config/org/cert?orgkey={org_key}',
        'https://ccadb-public.secure.force.com/mozilla/IncludedRootsPEMTxt?TrustBitsInclude=Websites'
    ]
    with open(f'{cert_dir}/{cert_name}', 'wb') as f:
        for url in urls:
            response = requests.get(url, verify=False)
            f.write(response.content)

if os.path.isfile(f'{cert_dir}/{cert_name}'):
    print(f'{cert_name} already exists in {cert_dir}.')
    recreate = input('Recreate Certificate Bundle? (y/N) ').strip().lower()
    if recreate == 'y':
        create_cert_bundle()
else:
    create_cert_bundle()

configured_tools_file = os.path.join(os.getcwd(), 'configured_tools.sh')
with open(configured_tools_file, 'w') as f:
    pass

def set_env_var(env_var, value):
    if is_windows:
        subprocess.run(f'setx {env_var} "{value}"', shell=True)
    else:
        with open(shell, 'a') as f:
            f.write(f'export {env_var}="{value}"\n')
        subprocess.run(f'source', shell=True)

def configure_tool(tool_name, env_var, check_command, post_command=None):
    print()
    if command_exists(check_command):
        print(f'{tool_name} is installed')
        subprocess.run(f'{check_command} --version', shell=True)
        if env_var:
            current_env = os.getenv(env_var)
            if current_env == f'{cert_dir}/{cert_name}':
                print(f'{tool_name} already configured')
            else:
                set_env_var(env_var, f'{cert_dir}/{cert_name}')
                print(f'{tool_name} configured')
                with open(configured_tools_file, 'a') as f:
                    if is_windows:
                        f.write(f'setx {env_var} "{cert_dir}/{cert_name}"\n')
                    else:
                        f.write(f'export {env_var}="{cert_dir}/{cert_name}"\n')
        if post_command:
            subprocess.run(post_command, shell=True)
            with open(configured_tools_file, 'a') as f:
                f.write(f'{post_command}\n')
    else:
        print(f'{tool_name} is not installed')

tools = [
    ("Git", "GIT_SSL_CAPATH", "git",""),
    ("OpenSSL", "SSL_CERT_FILE", "openssl",""),
    ("cURL", "SSL_CERT_FILE", "curl",""),
    ("Python Requests Library", "REQUESTS_CA_BUNDLE", "", ""),  # Adjusted this line
    ("AWS CLI", "AWS_CA_BUNDLE", "aws",""),
    ("Google Cloud CLI", None, "gcloud", f'gcloud config set core/custom_ca_certs_file {cert_dir}/{cert_name}'),
    ("NodeJS Package Manager (NPM)", None, "npm", f'npm config set cafile {cert_dir}/{cert_name}'),
    ("NodeJS", "NODE_EXTRA_CA_CERTS", "node",""),
    ("Ruby", "SSL_CERT_FILE", "ruby",""),
    ("PHP Composer", None, "composer", f'composer config --global cafile {cert_dir}/{cert_name}'),
    ("GoLang", "SSL_CERT_FILE", "go",""),
    ("Azure CLI", "REQUESTS_CA_BUNDLE", "az",""),
    ("Python PIP", "REQUESTS_CA_BUNDLE", "pip",""),
    ("Oracle Cloud CLI", "REQUESTS_CA_BUNDLE", "oci",""),
    ("Cargo Package Manager", "SSL_CERT_FILE", "cargo",""),
    ("Yarn", None, "yarnpkg", f'yarnpkg config set httpsCaFilePath {cert_dir}/{cert_name}')
]

for tool_name, env_var, check_command, post_command in tools:
    configure_tool(tool_name, env_var, check_command, post_command)

azure_storage_path = os.path.expanduser('~/Library/Application Support/StorageExplorer/certs') if not is_windows else os.path.join(os.getenv('USERPROFILE'), 'AppData', 'Roaming', 'StorageExplorer', 'certs')
if os.path.isdir(azure_storage_path):
    print('Azure Storage Explorer is installed')
    shutil.copy(f'{cert_dir}/{cert_name}', azure_storage_path)
    print('Azure Storage Explorer configured')
    with open(configured_tools_file, 'a') as f:
        f.write(f'cp "{cert_dir}/{cert_name}" "{azure_storage_path}"\n')
else:
    print('Azure Storage Explorer is not installed')

# Adding a new tool
# To add a new tool, use the `configure_tool` function with the appropriate parameters.
# Example:
# configure_tool("Tool Name", "ENV_VAR_NAME", "check_command", "post_command")
# - tool_name: The name of the tool (for display purposes)
# - env_var: The environment variable to set (if applicable)
# - check_command: The command to check if the tool is installed (usually the tool's executable name)
# - post_command: Any additional configuration command needed after setting the environment variable (can be empty if not needed)
#
# Example for adding a hypothetical tool "MyTool":
# configure_tool("MyTool", "MYTOOL_CA_CERTS", "mytool", f'mytool config set cafile {cert_dir}/{cert_name}')