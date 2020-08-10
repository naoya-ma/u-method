:go get github.com/akavel/rsrc
:cd %GOPATH%
@setlocal
@set apps=qmmd

go build -o %apps%.exe

if exist dist\%apps%_windows_amd64 (
  copy /y %apps%.exe  dist\%apps%_windows_amd64
)
