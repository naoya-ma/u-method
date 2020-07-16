package main

import (
	"bufio"
	"fmt"
	"os"
	"strings"

	goquery "github.com/PuerkitoBio/goquery"
	flags "github.com/jessevdk/go-flags"
)

type Options struct {
	Verbose []bool `short:"v" long:"verbose" description:"Show verbose debug information"`
}

var opts Options

func containsAnyString(target string, anystr ...string) bool {
	flag := false

	for _, str := range anystr {
		if strings.Contains(target, str) {
			flag = true
			break
		}
	}
	return flag
}

func main() {

	parser := flags.NewParser(&opts, flags.Default)
	parser.Name = "tg"
	parser.Usage = "[OPTIONS]"

	args, _ := parser.Parse()
	if len(args) != 0 {
		parser.WriteHelp(os.Stdout)
		os.Exit(1)
	}

	var urlpath, title string
	input := bufio.NewScanner(os.Stdin)
	for input.Scan() {
		urlpath = strings.TrimSpace(input.Text())
		if len(urlpath) > 0 {
			//^http:|^https:|^file:|^ftp:
			if containsAnyString(urlpath, "http://", "https://", "file://", "ftp://") {
				title = "(unknown)"
				doc, err := goquery.NewDocument(urlpath)
				if err != nil {
					fmt.Fprintf(os.Stderr, "[ERROR] %v\n", err)
				} else {
					title = strings.TrimSpace(doc.Find("title").Text())
				}
				fmt.Printf("* %s\n", title)
				fmt.Printf("  %s\n", urlpath)
			} else {
				fmt.Printf("* %s\n", urlpath)
			}
		}
	}

}
