@:go get github.com/akavel/rsrc
@:cd %GOPATH%

@setlocal
@set apps=gwebci
@set appsdir=gwebc

@pushd %appsdir%

@:rsrc -manifest %apps%.exe.manifest -ico %apps%.ico -o %apps%.syso
@rsrc -manifest %apps%.exe.manifest -o %apps%.syso

go build -ldflags="-H windowsgui"

if exist dist\%apps%_windows_amd64 (
  copy /y %apps%.exe  dist\%apps%_windows_amd64
)

if exist ..\dist\%apps%_windows_amd64 (
  copy /y %apps%.exe  ..\dist\%apps%_windows_amd64
)

@popd
