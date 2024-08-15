#!/bin/bash
## This tool will try to detect common cli tools and will configure the Netskope SSL certificate bundle.

# Check which shell environment is used (zsh or bash)
get_shell(){
    my_shell=$(echo $SHELL)
    echo "Shell used is $my_shell"
    if [[ $my_shell == *"bash"* ]]; then
        shell=~/.bash_profile
    else
        shell=~/.zshenv
    fi
}
get_shell

# Set Certificate bundle name and location
read -p "Please provide certificate bundle name [netskope-cert-bundle.pem]: " certName
certName=${certName:-netskope-cert-bundle.pem}
read -p "Please provide certficate bundle location [~/netskope]: " certDir
certDir=${certDir:-~/netskope}
if [ ! -d "$certDir" ]; then
  echo "$certDir does not exist."
  echo "creating $certDir"
  mkdir -p $certDir
fi

# Get tenant information to create certificate bundle
read -p "Please provide full tenant name (ex: mytenant.eu.goskope.com): " tenantName
read -p "Please provide tenant orgkey: " orgKey

status_code=$(curl -k --write-out %{http_code} --silent --output /dev/null https://$tenantName/locallogin)

if [[ "$status_code" -ne "307" ]] ; then
  echo "Tenant Unreachable"
  exit 1
else
  echo "Tenant Reachable"
fi

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Function to create or update certificate bundle
create_cert_bundle() {
  echo "Creating cert bundle"
  curl -k "https://addon-$tenantName/config/ca/cert?orgkey=$orgKey" > $certDir/$certName
  curl -k "https://addon-$tenantName/config/org/cert?orgkey=$orgKey" >> $certDir/$certName
  curl -k -L "https://ccadb-public.secure.force.com/mozilla/IncludedRootsPEMTxt?TrustBitsInclude=Websites" >> $certDir/$certName
}

if [ -f "$certDir/$certName" ]; then
  echo "$certName already exists in $certDir."
  read -p "Recreate Certificate Bundle? (y/N) " -n 1 -r
  echo    
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    create_cert_bundle
  fi
else
  create_cert_bundle
fi

# Function to configure a tool with the certificate bundle
configure_tool() {
  local tool_name=$1
  local env_var=$2
  local check_command=$3
  local post_command=$4

  echo
  if command_exists $check_command; then
    echo "$tool_name is installed"
    $check_command --version
    if [[ -n "$env_var" ]]; then
      if [[ ${!env_var} == "$certDir/$certName" ]]; then
        echo "$tool_name already configured"
      else
        echo "export $env_var=\"$certDir/$certName\"" >> $shell
        echo "$tool_name configured"
        source $shell
        echo "export $env_var=\"$certDir/$certName\"" >> configured_tools.sh
      fi
    fi
    if [[ -n "$post_command" ]]; then
      eval $post_command
      echo "$post_command" >> configured_tools.sh
    fi
  else
    echo "$tool_name is not installed"
  fi
}

# This allows for later silent runs on other machines
> configured_tools.sh

# Configure tools
configure_tool "Git" "GIT_SSL_CAPATH" "git" ""
configure_tool "OpenSSL" "SSL_CERT_FILE" "openssl" ""
configure_tool "cURL" "SSL_CERT_FILE" "curl" ""
configure_tool "Python Requests Library" "REQUESTS_CA_BUNDLE" "" ""
configure_tool "AWS CLI" "AWS_CA_BUNDLE" "awscli" ""
configure_tool "Google Cloud CLI" "" "gcloud" "gcloud config set core/custom_ca_certs_file $certDir/$certName"
configure_tool "NodeJS Package Manager (NPM)" "" "npm" "npm config set cafile $certDir/$certName"
configure_tool "NodeJS" "NODE_EXTRA_CA_CERTS" "node" ""
configure_tool "Ruby" "SSL_CERT_FILE" "ruby" ""
configure_tool "PHP Composer" "" "composer" "composer config --global cafile $certDir/$certName"
configure_tool "GoLang" "SSL_CERT_FILE" "go" ""
configure_tool "Azure CLI" "REQUESTS_CA_BUNDLE" "az" ""
configure_tool "Python PIP" "REQUESTS_CA_BUNDLE" "pip3" ""
configure_tool "Oracle Cloud CLI" "REQUESTS_CA_BUNDLE" "oci-cli" ""
configure_tool "Cargo Package Manager" "SSL_CERT_FILE" "cargo" ""
configure_tool "Yarn" "" "yarnpkg" "yarnpkg config set httpsCaFilePath $certDir/$certName"

# Check if Azure Storage Explorer exists
echo
if [ -d ~/Library/Application\ Support/StorageExplorer/certs ]; then
  echo "Azure Storage Explorer is installed"
  cp "$certDir/$certName" ~/Library/Application\ Support/StorageExplorer/certs
  echo "Azure Storage Explorer configured"
  echo "cp \"$certDir/$certName\" ~/Library/Application\ Support/StorageExplorer/certs" >> configured_tools.sh
else
  echo "Azure Storage Explorer is not installed"
fi

# Adding a new tool
# To add a new tool, use the `configure_tool` function with the appropriate parameters.
# Example:
# configure_tool "Tool Name" "ENV_VAR_NAME" "check_command" "post_command"
# - tool_name: The name of the tool (for display purposes)
# - env_var: The environment variable to set (if applicable)
# - check_command: The command to check if the tool is installed (usually the tool's executable name)
# - post_command: Any additional configuration command needed after setting the environment variable (can be empty if not needed)
#
# Example for adding a hypothetical tool "MyTool":
# configure_tool "MyTool" "MYTOOL_CA_CERTS" "mytool" "mytool config set cafile $certDir/$certName"
