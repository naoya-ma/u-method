package main

import (
	"bufio"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/jessevdk/go-flags"
	"github.com/lxn/walk"
	. "github.com/lxn/walk/declarative"
)

const myCmdName = "gwebc"
const myCmdTitle = "getWebContents"

type Options struct {
	Verbose bool `short:"v" long:"verbose" description:"Show verbose debug information"`
	Cui     bool `short:"c" long:"cui" description:"CUI Mode"`
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

type MyMainWindow struct {
	*walk.MainWindow
	inputArea  *walk.TextEdit
	chk1       *walk.CheckBox
	outputArea *walk.TextEdit
}

func (mw *MyMainWindow) buttonClicked() {
	var urlpath, title, ogtitle string
	var splitLine []string
	originalText := mw.inputArea.Text()
	splitLine = strings.Split(strings.Replace(originalText, "\r\n", "\n", -1), "\n")

	// goroutine
	finished := make(chan bool)

	go func() {
		start := time.Now()

		//mw.outputArea.SetEnabled(false)

		for i := 0; i < len(splitLine); i++ {
			urlpath = strings.TrimSpace(splitLine[i])
			if len(urlpath) > 0 {
				if containsAnyString(urlpath, "http://", "https://", "file://", "ftp://") {
					title = urlpath //title = "(unknown)"
					ogtitle = ""
					doc, err := goquery.NewDocument(urlpath)
					if err != nil {
						log.Print(fmt.Sprintf("[ERROR] %v\n", err))
					} else {
						// get title
						title = strings.TrimSpace(doc.Find("title").Text())
						// get meta description field
						doc.Find("meta").Each(func(j int, s *goquery.Selection) {
							op, _ := s.Attr("property")
							con, _ := s.Attr("content")
							if opts.Verbose {
								log.Print(fmt.Sprintf("-- [%s]:[%s]\n", op, con))
							}
							if op == "og:title" {
								ogtitle = con
								//fmt.Printf("ogtitle field: %s\n", ogtitle)
								if len(ogtitle) > 0 {
									title = ogtitle
								}
							}
						})
					}
					mw.outputArea.AppendText(fmt.Sprintf("* %s\r\n  %s\r\n", title, urlpath))
				} else {
					if mw.chk1.CheckState() != walk.CheckChecked {
						mw.outputArea.AppendText(fmt.Sprintf("%s\r\n", urlpath))
					}
				}
			}
		}

		//mw.outputArea.SetEnabled(true)

		elapsed := time.Since(start)
		mw.outputArea.AppendText(fmt.Sprintf("elapsed %s\r\n", elapsed))

		finished <- true
	}()

	//<-finished

}

func (mw *MyMainWindow) check1Changed() {
	if opts.Verbose {
		log.Println("Event: CHK1 changed")
	}
}

func executeByCui() {
	var urlpath, title, ogtitle string

	input := bufio.NewScanner(os.Stdin)
	for input.Scan() {
		urlpath = input.Text()
		if len(urlpath) > 0 {
			if containsAnyString(urlpath, "http://", "https://", "file://", "ftp://") {
				title = urlpath //title = "(unknown)"
				ogtitle = ""
				doc, err := goquery.NewDocument(urlpath)
				if err != nil {
					fmt.Fprintf(os.Stderr, "[ERROR] %v\n", err)
				} else {
					// get title
					title = strings.TrimSpace(doc.Find("title").Text())
					// get meta description field
					doc.Find("meta").Each(func(j int, s *goquery.Selection) {
						op, _ := s.Attr("property")
						con, _ := s.Attr("content")
						if opts.Verbose {
							fmt.Printf("-- [%s]:[%s]\n", op, con)
						}
						if op == "og:title" {
							ogtitle = con
							//fmt.Printf("ogtitle field: %s\n", ogtitle)
							if len(ogtitle) > 0 {
								title = ogtitle
							}
						}
					})
				}
				fmt.Printf("* %s\n", title)
				fmt.Printf("  %s\n", urlpath)
			} else {
				fmt.Printf("* %s\n", urlpath)
			}
		}
	}

}

func main() {

	// Parse Command Operation
	parser := flags.NewParser(&opts, flags.Default)
	parser.Name = myCmdName
	parser.Usage = "[OPTIONS]"

	args, err := parser.Parse()
	if err != nil {
		os.Exit(1)
	}
	if len(args) != 0 {
		parser.WriteHelp(os.Stdout)
		os.Exit(1)
	}

	// Distributing processing
	if opts.Cui {
		// CUI mode
		executeByCui()
	} else {
		// GUI mode
		mw := &MyMainWindow{}
		if _, err := (MainWindow{
			AssignTo: &mw.MainWindow,
			Title:    myCmdTitle,
			MinSize:  Size{400, 100},
			Size:     Size{500, 400},
			Layout:   VBox{},
			Children: []Widget{
				GroupBox{
					Title:  "Input",
					Layout: VBox{},
					Children: []Widget{
						TextEdit{
							AssignTo: &mw.inputArea,
							VScroll:  true,
						},
						GroupBox{
							Layout: HBox{},
							Children: []Widget{
								CheckBox{
									AssignTo:         &mw.chk1,
									Text:             "URL Only",
									Checked:          false,
									OnCheckedChanged: mw.check1Changed,
								},
								PushButton{
									Text:      "Get",
									OnClicked: mw.buttonClicked,
								},
							},
						},
					},
				},
				GroupBox{
					Title:  "Output",
					Layout: HBox{},
					Children: []Widget{
						TextEdit{
							AssignTo: &mw.outputArea,
							VScroll:  true,
						},
					},
				},
			},
		}.Run()); err != nil {
			log.Fatal(err)
		}
	}

}
