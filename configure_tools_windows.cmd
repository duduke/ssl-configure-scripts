@echo off
:: This tool will try to detect common cli tools and will configure the Netskope SSL certificate bundle.

:: Set Certificate bundle name and location
set /p certName="Please provide certificate bundle name [netskope-cert-bundle.pem]:"
if "%certName%"=="" set certName=netskope-cert-bundle.pem

set /p certDir="Please provide certificate bundle location [C:\netskope]:"
if "%certDir%"=="" set certDir=C:\netskope

if not exist "%certDir%" (
    echo %certDir% does not exist.
    echo Creating %certDir%
    mkdir "%certDir%"
)

:: Get tenant information to create certificate bundle
set /p tenantName="Please provide full tenant name (ex: mytenant.eu.goskope.com):"
set /p orgKey="Please provide tenant orgkey:"

:: Check tenant reachability
curl -k --write-out "%%{http_code}" --silent --output NUL https://%tenantName%/locallogin > temp.txt
set /p status_code=<temp.txt
del temp.txt

if "%status_code%" NEQ "307" (
    echo Tenant Unreachable
    exit /b 1
) else (
    echo Tenant Reachable
)

:: Create or update certificate bundle
set certBundleExists=0
if exist "%certDir%\%certName%" (
    echo %certName% already exists in %certDir%.
    set /p recreate="Recreate Certificate Bundle? (y/n): "
    if /i "%recreate%"=="y" set certBundleExists=1
) else (
    set certBundleExists=1
)

if %certBundleExists%==1 (
    echo Creating cert bundle
    curl -k "https://addon-%tenantName%/config/ca/cert?orgkey=%orgKey%" > "%certDir%\%certName%"
    curl -k "https://addon-%tenantName%/config/org/cert?orgkey=%orgKey%" >> "%certDir%\%certName%"
    curl -k -L "https://curl.se/ca/cacert.pem" >> "%certDir%\%certName%"
)

:: Tools configuration (add more tools here as needed)

:: Initialize configured tools file
echo @echo off > configured_tools.bat

echo.
call :command_exists git
if %ERRORLEVEL% EQU 0 call :configure_tool git "git config --global http.sslCAInfo" "git config --global http.sslCAInfo" "git config --global http.sslCAInfo %certDir%\%certName%"

echo.
call :command_exists openssl
if %ERRORLEVEL% EQU 0 call :configure_tool openssl "openssl version -a" "setx SSL_CERT_FILE" "setx SSL_CERT_FILE %certDir%\%certName%"

echo.
call :command_exists curl
if %ERRORLEVEL% EQU 0 call :configure_tool curl "curl --version" "setx SSL_CERT_FILE" "setx SSL_CERT_FILE %certDir%\%certName%"

echo.
set REQUESTS_CA_BUNDLE=
for /f "tokens=*" %%P in ('python -m requests') do (
    if "%%P"=="built on:" set REQUESTS_CA_BUNDLE=%%P
)
if "%REQUESTS_CA_BUNDLE%"=="%certDir%\%certName%" (
    echo Python Requests Already configured
) else (
    setx REQUESTS_CA_BUNDLE "%certDir%\%certName%"
    echo Python Requests Library Configured
    echo setx REQUESTS_CA_BUNDLE "%certDir%\%certName%" >> configured_tools.bat
)

echo.
call :command_exists aws
if %ERRORLEVEL% EQU 0 call :configure_tool aws "aws --version" "setx AWS_CA_BUNDLE" "setx AWS_CA_BUNDLE %certDir%\%certName%"

echo.
call :command_exists gcloud
if %ERRORLEVEL% EQU 0 (
    echo Google Cloud CLI is installed
    gcloud --version
    gcloud config set core/custom_ca_certs_file %certDir%\%certName%
    echo Google Cloud CLI Configured
    echo gcloud config set core/custom_ca_certs_file %certDir%\%certName% >> configured_tools.bat
) else (
    echo Google Cloud CLI is not installed
)

echo.
call :command_exists npm
if %ERRORLEVEL% EQU 0 (
    echo "NodeJS Package Manager (NPM) is installed"
    npm --version
    npm config set cafile %certDir%\%certName%
    echo "NodeJS Package Manager (NPM) Configured"
    echo npm config set cafile %certDir%\%certName% >> configured_tools.bat
) else (
    echo "NodeJS Package Manager (NPM) is not installed"
)

echo.
call :command_exists node
if %ERRORLEVEL% EQU 0 call :configure_tool node "node --version" "setx NODE_EXTRA_CA_CERTS" "setx NODE_EXTRA_CA_CERTS %certDir%\%certName%"

echo.
call :command_exists ruby
if %ERRORLEVEL% EQU 0 call :configure_tool ruby "ruby --version" "setx SSL_CERT_FILE" "setx SSL_CERT_FILE %certDir%\%certName%"

echo.
call :command_exists composer
if %ERRORLEVEL% EQU 0 (
    echo PHP Composer is installed
    composer --version
    composer config --global cafile %certDir%\%certName%
    echo PHP Composer Configured
    echo composer config --global cafile %certDir%\%certName% >> configured_tools.bat
) else (
    echo PHP Composer is not installed
)

echo.
call :command_exists go
if %ERRORLEVEL% EQU 0 call :configure_tool go "go --version" "setx SSL_CERT_FILE" "setx SSL_CERT_FILE %certDir%\%certName%"

echo.
call :command_exists az
if %ERRORLEVEL% EQU 0 call :configure_tool az "az --version" "setx REQUESTS_CA_BUNDLE" "setx REQUESTS_CA_BUNDLE %certDir%\%certName%"

echo.
call :command_exists pip
if %ERRORLEVEL% EQU 0 call :configure_tool pip "pip --version" "setx REQUESTS_CA_BUNDLE" "setx REQUESTS_CA_BUNDLE %certDir%\%certName%"

echo.
call :command_exists oci
if %ERRORLEVEL% EQU 0 call :configure_tool oci "oci --version" "setx REQUESTS_CA_BUNDLE" "setx REQUESTS_CA_BUNDLE %certDir%\%certName%"

echo.
call :command_exists cargo
if %ERRORLEVEL% EQU 0 (
    echo Cargo Package Manager is installed
    cargo --version
    set SSL_CERT_FILE=
    for /f "tokens=*" %%P in ('cargo --version') do (
        if "%%P"=="built on:" set SSL_CERT_FILE=%%P
    )
    if "%SSL_CERT_FILE%"=="%certDir%\%certName%" (
        echo Cargo Package Manager Already configured 1/2
    ) else (
        setx SSL_CERT_FILE "%certDir%\%certName%"
        echo setx SSL_CERT_FILE "%certDir%\%certName%" >> configured_tools.bat
    )
    set GIT_SSL_CAPATH=
    for /f "tokens=*" %%P in ('cargo --version') do (
        if "%%P"=="built on:" set GIT_SSL_CAPATH=%%P
    )
    if "%GIT_SSL_CAPATH%"=="%certDir%\%certName%" (
        echo Cargo Package Manager Already configured 2/2
    ) else (
        setx GIT_SSL_CAPATH "%certDir%\%certName%"
        echo setx GIT_SSL_CAPATH "%certDir%\%certName%" >> configured_tools.bat
    )
    echo Cargo Package Manager configured
) else (
    echo Cargo Package Manager is not installed
)

echo.
call :command_exists yarn
if %ERRORLEVEL% EQU 0 (
    echo Yarn is installed
    yarn --version
    yarn config set cafile %certDir%\%certName%
    echo Yarn Configured
    echo yarn config set cafile %certDir%\%certName% >> configured_tools.bat
) else (
    echo Yarn is not installed
)

:: Function to check if a command exists
:command_exists
where %1 > NUL 2>&1
if %ERRORLEVEL% EQU 0 (
    exit /b 0
) else (
    exit /b 1
)

:: Function to configure tools
:configure_tool
:: %1 - Tool name
:: %2 - Command to retrieve the current configuration
:: %3 - Command to set the new configuration
:: %4 - Command to log configuration
echo %~1 is installed
%~1 --version
set toolConfigured=0
for /f "tokens=*" %%P in ('%~2') do set toolConfigured=%%P
if "%toolConfigured%"=="%certDir%\%certName%" (
    echo %~1 Already configured
) else (
    %~3 "%certDir%\%certName%"
    echo %~1 Configured
    echo %~1 Configured
    echo %~4 >> configured_tools.bat
)
exit /b 0
:: How to add a new tool:
:: 1. Add a call to :command_exists followed by the tool name (e.g., "call :command_exists mytool").
:: 2. If the tool is found (ERRORLEVEL is 0), call :configure_tool with the following parameters:
::    - Tool name (e.g., "mytool")
::    - Command to retrieve the current configuration (e.g., "mytool config --global cafile")
::    - Command to set the new configuration (e.g., "mytool config --global cafile")
::    - Command to log configuration (e.g., "mytool config --global cafile %certDir%\%certName%" >> configured_tools.bat)
:: Example:
:: echo.
:: call :command_exists mytool
:: if %ERRORLEVEL% EQU 0 call :configure_tool mytool "mytool config --global cafile" "mytool config --global cafile" "mytool config --global cafile %certDir%\%certName%" >> configured_tools.bat
