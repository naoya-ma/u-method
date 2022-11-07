FROM almalinux:9

RUN set -eux ; \
#   dnf clean all; \
#   dnf -y update ; \
    dnf -y makecache; \
    dnf -y install unzip git sudo make xz patch; \
    dnf -y install epel-release; \
    dnf -y install yum-utils; \
    rpm -ivh http://packages.groonga.org/almalinux/9/groonga-release-latest.noarch.rpm --nosignature; \
    dnf -y install mecab mecab-ipadic --nogpgcheck; \
    dnf -y install mecab-devel --nogpgcheck; \
    dnf -y install python3 python3-pip; \
    pip3 install mecab-python3; \
    mkdir /data

RUN cd /usr/local/src; \
    git clone --depth 1 https://github.com/neologd/mecab-ipadic-neologd.git; \
    dnf -y install which diffutils file; \ 
    dnf -y install glibc-gconv-extra; \ 
    cd mecab-ipadic-neologd; \
    ./bin/install-mecab-ipadic-neologd -n -a -y; \
    echo "dicdir = /usr/lib64/mecab/dic/mecab-ipadic-neologd/" >> /etc/mecabrc ; \
    ln -s /etc/mecabrc /usr/local/etc/mecabrc

RUN dnf -y groupinstall "Development tools" ; \
    dnf -y install python3-devel; \
    dnf -y install wget; \
    cd /usr/local/src; \
    pip3 install wheel ; \
    pip3 install git+https://github.com/facebookresearch/fastText.git@v0.9.2 ;\
    pip3 install pandas sklearn 

SHELL ["/bin/bash", "-l", "-c"] 

# -----------------------------------------------------
# Mecab(BSD,LGPL,GPL License)
# https://taku910.github.io/mecab/
#
# neologd (Apache License)
# echo `mecab-config --dicdir`"/mecab-ipadic-neologd"
# /usr/lib64/mecab/dic/mecab-ipadic-neologd
# https://github.com/neologd/mecab-ipadic-neologd/blob/master/COPYING
#
# fasttext (MIT License)
# https://fasttext.cc/docs/en/python-module.html
# https://github.com/facebookresearch/fastText/blob/main/LICENSE
# 
