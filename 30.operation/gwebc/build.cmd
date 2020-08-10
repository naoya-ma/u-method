@:go get github.com/akavel/rsrc
@:cd %GOPATH%

@pushd gwebc

@:rsrc -manifest gwebc.exe.manifest -ico gwebc.ico -o gwebc.syso
@rsrc -manifest gwebc.exe.manifest -o gwebc.syso

go build -ldflags="-H windowsgui"

if exist dist\gwebc_windows_amd64 (
  copy /y gwebc.exe dist\gwebc_windows_amd64
)

if exist ..\dist\gwebc_windows_amd64 (
  copy /y gwebc.exe ..\dist\gwebc_windows_amd64
)

@popd
