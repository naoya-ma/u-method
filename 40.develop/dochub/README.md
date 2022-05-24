# dochub

### 1.  Component

"dochub" is a collection of document creation tools that are often used in the design and development process. We have a text code-based tool that is ideal for maintenance.

- [plantUML](https://plantuml.com/), [Graphviz](https://graphviz.org/)  with java
- [uiflow](https://github.com/hirokidaichi/uiflow) with nodejs
- [blockdiag](https://github.com/blockdiag/blockdiag) with python3
- [nwdiag](https://github.com/blockdiag/nwdiag) with python3
- [diagrams](https://github.com/mingrammer/diagrams) with python3
- [asciidoctor](https://asciidoctor.org/) with ruby
- [mkdocs](https://www.mkdocs.org/) with python3

### 2. Install and Run

<details>
<summary>Instructions</summary>

#### Windows 11 + [WSL 2](https://docs.microsoft.com/windows/wsl/)(ubuntu)

```
> wsl
# cd /data
# docker-compose down && docker-compose build && docker-compose --publish 8000:8000 run dochub
# cd /data/project
# mkdocs serve -a 0.0.0.0:8000
```
</details> 

### 3. Usage


```
# cd /data
# mkdocs serve -a 0.0.0.0:8000
```

