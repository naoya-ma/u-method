@:go get github.com/akavel/rsrc
@:cd %GOPATH%

@pushd gwebc

go build -o gwebc-cui.exe

if exist dist\gwebc-cui_windows_amd64 (
  copy /y gwebc-cui.exe  dist\gwebc-cui_windows_amd64
)

if exist ..\dist\gwebc-cui_windows_amd64 (
  copy /y gwebc-cui.exe  ..\dist\gwebc-cui_windows_amd64
)

@popd

