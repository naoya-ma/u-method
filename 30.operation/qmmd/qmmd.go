package main

import (
	"fmt"
	"io"
	"os"
	"strconv"
	"time"

	"github.com/jessevdk/go-flags"
)

const myCmdName = "qmmd"
const DEBUG = false

type Options struct {
	Template        bool `short:"t" long:"template" description:"template copy mode"`
	PreviousWeekDir bool `short:"p" long:"previous" description:"previosWeek-dir copy mode"`
}

var opts Options

func LastWeekDay(today time.Time, weekofday int) string {
	var rs string
	rs = today.AddDate(0, 0, -7+weekofday-int(today.Weekday())).Format("20060102")
	return rs
}

func ThisWeekDay(today time.Time, weekofday int) string {
	var rs string
	rs = today.AddDate(0, 0, weekofday-int(today.Weekday())).Format("20060102")
	return rs
}

func NextWeekDay(today time.Time, weekofday int) string {
	var rs string
	rs = today.AddDate(0, 0, 7+weekofday-int(today.Weekday())).Format("20060102")
	return rs
}

func IsDirExist(dir string) (bool, error) {
	fInfo, err := os.Stat(dir)
	if err != nil {
		if os.IsExist(err) == false {
			return false, nil //Directory does not exist
		} else {
			return false, err //Something wrong
		}
	} else {
		if fInfo.IsDir() == false {
			return false, nil //regular file
		}
	}
	return true, nil
}

func CopyFile(source string, dest string) (err error) {
	sourcefile, err := os.Open(source)
	if err != nil {
		return err
	}

	defer sourcefile.Close()

	destfile, err := os.Create(dest)
	if err != nil {
		return err
	}

	defer destfile.Close()

	_, err = io.Copy(destfile, sourcefile)
	if err == nil {
		sourceinfo, err := os.Stat(source)
		if err != nil {
			err = os.Chmod(dest, sourceinfo.Mode())
		}

	}

	return
}

func CopyDir(src string, dest string, fileCopy bool) (err error) {

	// get properties of source dir
	srcinfo, err := os.Stat(src)
	if err != nil {
		return err
	}

	// create dest dir
	err = os.MkdirAll(dest, srcinfo.Mode())
	if err != nil {
		return err
	}

	dir, _ := os.Open(src)
	objs, err := dir.Readdir(-1)

	for _, obj := range objs {

		srcfile := src + "/" + obj.Name()
		destfile := dest + "/" + obj.Name()

		if obj.IsDir() { // create sub-directories - recursively
			err = CopyDir(srcfile, destfile, fileCopy)
			if err != nil {
				fmt.Fprintln(os.Stderr, err)
			}
		} else {
			if fileCopy { // filecopy
				err = CopyFile(srcfile, destfile)
				if err != nil {
					fmt.Fprintln(os.Stderr, err)
				}
			}
		}
	}
	return
}

func main() {

	// Parse Command Operation
	parser := flags.NewParser(&opts, flags.Default)
	parser.Name = myCmdName
	parser.Usage = `[OPTIONS] basedir weekofday directorySuffix
	weekofday       : Sunday=0,Monday=1, Tuesday=2, Wednesday=3, Thursday=4, Friday=5, Saturday=6
	directorySuffix : string
	ex.  qmmd meetingdir 1 LeaderMeeting /t
	     qmmd meetingdir 2 DevMeeting /p`

	args, err := parser.Parse()
	if err != nil {
		os.Exit(1)
	}
	if len(args) < 3 {
		//parser.WriteHelp(os.Stdout)
		os.Exit(1)
	}

	// Parse argument
	basedir := args[0]
	var weekofday int
	weekofday, _ = strconv.Atoi(args[1])
	directorySuffix := args[2]

	if DEBUG {
		fmt.Println(basedir)
		fmt.Println(weekofday)
		fmt.Println(directorySuffix)
	}

	today := time.Now()
	if DEBUG {
		//https://github.com/golang/go/blob/master/src/time/format.go
		const layout = "2006012"
		todayStr := today.Format(layout)

		fmt.Printf("today: %s\n", todayStr)
		fmt.Printf("LastWeek: Last %s\n", LastWeekDay(today, weekofday))
		fmt.Printf("ThisWeek: This %s\n", ThisWeekDay(today, weekofday))
		fmt.Printf("NextWeek: Next %s\n", NextWeekDay(today, weekofday))
	}

	destDir := basedir + "/" + NextWeekDay(today, weekofday) + "-" + directorySuffix
	if rc, err := IsDirExist(destDir); rc {
		fmt.Printf("ERROR:Directory exist.Dir=%s\n", destDir)
		os.Exit(1)
	} else {
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	}

	if opts.PreviousWeekDir {
		srcDir := basedir + "/" + ThisWeekDay(today, weekofday) + "-" + directorySuffix
		if f, err := os.Stat(srcDir); os.IsNotExist(err) || !f.IsDir() {
			fmt.Fprintf(os.Stderr, "ERROR:PreviousWeekDir not Found. Dir=%s\n", srcDir)
			os.Exit(1)
		}
		err := CopyDir(srcDir, destDir, false)
		if err != nil {
			fmt.Fprintf(os.Stderr, "ERROR:Can not Copy. srcDir=%s, destDir=%s\n", srcDir, destDir)
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	} else if opts.Template {
		srcDir := basedir + "/00Template" + "-" + directorySuffix
		if f, err := os.Stat(srcDir); os.IsNotExist(err) || !f.IsDir() {
			fmt.Fprintf(os.Stderr, "ERROR:TemplateDir not Found. Dir=%s\n", srcDir)
			os.Exit(1)
		}
		err := CopyDir(srcDir, destDir, true)
		if err != nil {
			fmt.Fprintf(os.Stderr, "ERROR:Can not Copy. srcDir=%s, destDir=%s\n", srcDir, destDir)
			fmt.Fprintf(os.Stderr, "%s\n", srcDir, destDir)
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}

	} else {
		//fmt.Fprintf(os.Stderr, "INFO: destDir=%s\n", destDir)
		if err := os.Mkdir(destDir, 0755); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	}
	fmt.Fprintf(os.Stderr, "INFO: Completed. destDir=%s\n", destDir)
	os.Exit(0)

}
