:go get github.com/akavel/rsrc
:cd %GOPATH%

go build -o gwebc-cui.exe

if exist dist\gwebc_windows_amd64 (
  copy /y gwebc-cui.exe  dist\gwebc_windows_amd64
)
