:go get github.com/akavel/rsrc
:cd %GOPATH%

go build -o gwebc-cui.exe

rsrc -manifest gwebc.exe.manifest -ico gwebc.ico -o gwebc..syso
go build -ldflags="-H windowsgui"