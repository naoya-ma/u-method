#syntax = docker/dockerfile:1.3-labs
FROM rockylinux:8.5
#-----------------------------------------------------
# install: java, plantuml
#-----------------------------------------------------
RUN set -eux ;
RUN dnf -y install which
RUN dnf -y install java-1.8.0-openjdk java-1.8.0-openjdk-devel graphviz
#-----------------------------------------------------
RUN mkdir -p /opt/plantuml
WORKDIR /opt/plantuml
ENV UML="http://sourceforge.net/projects/plantuml/files/plantuml.jar/download" 
RUN curl -JLO ${UML}
RUN { \
    echo '#!/bin/sh'; \
    echo 'java -jar /opt/plantuml/plantuml.jar \"\$@\"'; \
    } > /usr/local/bin/plantuml
RUN set -eux ; \
  chmod 755 /usr/local/bin/plantuml
RUN set -eux ; \
  dnf -y install langpacks-ja 
#        vlgothic-fonts vlgothic-p-fonts  \
#        google-noto-cjk-fonts-common google-noto-sans-cjk-ttc-fonts google-noto-serif-cjk-ttc-fonts
#-----------------------------------------------------
# install: python3, mkdocs
#-----------------------------------------------------
RUN set -eux ; \
    dnf -y install python3 
RUN pip3 install --upgrade pip
RUN pip3 install mkdocs
RUN pip3 install mkdocs-material
RUN pip3 install fontawesome_markdown

#-----------------------------------------------------
# install: blockdiag, nwdiag
#-----------------------------------------------------
RUN pip3 install blockdiag nwdiag

#-----------------------------------------------------
# install: diagrams
#-----------------------------------------------------
RUN pip3 install diagrams

#-----------------------------------------------------
# install: ruby3,
#-----------------------------------------------------
RUN set -eux ; \
  dnf module reset ruby -y && dnf install -y @ruby:3.0
#-----------------------------------------------------
# install: rbenv, ruby3.1, asciidoctor
#-----------------------------------------------------
RUN set -eux ; \
  dnf -y install git make gcc curl openssl-devel zlib-devel libffi-devel readline-devel sqlite-devel
RUN curl -fsSL https://github.com/rbenv/rbenv-installer/raw/HEAD/bin/rbenv-installer | bash
RUN { \
    echo 'export PATH="$HOME/.rbenv/bin:$PATH"' ; \
    echo 'eval "$(rbenv init -)"' ; \
    } > ~/.bashrc
RUN source ~/.bashrc && \
  rbenv install 3.1.2 && rbenv global 3.1.2 
RUN gem install asciidoctor
RUN gem install asciidoctor-diagram
RUN gem install thread_safe asciidoctor-pdf

#-----------------------------------------------------
# install: nodejs, npm, uiflow
#-----------------------------------------------------
RUN dnf module reset nodejs  -y
RUN dnf -y install @nodejs:16 npm
RUN npm -y install -g n && n stable && dnf -y remove nodejs npm
RUN npm -y install -g uiflow
#RUN exec $SHELL -l

#-----------------------------------------------------
# test: version
#-----------------------------------------------------
RUN  \
  set -eux ; \
  python3 --version; \
  ruby -v; \
  node -v; \
  npm -v; \
  asciidoctor -v; \
  java -showversion |& head -3; \
  plantuml  -v; \
  nwdiag --version \
  blockdiag --version ; \
  pip3 list | grep -e diagrams -e graphviz 
# yum install iproute
