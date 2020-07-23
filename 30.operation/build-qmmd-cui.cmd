@:go get github.com/akavel/rsrc
@:cd %GOPATH%

@setlocal
@set apps=qmmd
@set appsdir=%apps%

@pushd %appsdir%

go build -o %apps%.exe

if exist dist\%apps%_windows_amd64 (
  copy /y %apps%.exe  dist\%apps%_windows_amd64
)

if exist ..\dist\%apps%_windows_amd64 (
  copy /y %apps%.exe  ..\dist\%apps%_windows_amd64
)

@popd
