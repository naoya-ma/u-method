FROM ubuntu:20.04

RUN apt-get update \
    && apt-get install -y unzip curl vim

RUN curl -sL https://deb.nodesource.com/setup_16.x | bash - \
    && apt-get install -y nodejs

WORKDIR /usr/local/test
COPY ./sample.spec.ts /usr/local/test


RUN npx playwright install-deps

RUN npx playwright install

# npx playwright codegen https://www.google.com
# npx playwright test
# npm i -D @playwright/test
# npx folio
