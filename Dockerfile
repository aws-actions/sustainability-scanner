# Container image that runs your code
FROM python:3.9-alpine

# Install required libs
RUN apk --no-cache add curl; \
    apk --no-cache add git; \
    apk --no-cache add bash

# Install CFN Guard
RUN curl --proto '=https' --tlsv1.2 -sSf https://raw.githubusercontent.com/aws-cloudformation/cloudformation-guard/main/install-guard.sh | sh
ENV PATH="/root/.guard/bin:${PATH}"

# Install AWS SusScan
RUN pip3 install sustainability-scanner

# Uninstall libs
RUN apk del git; \
    apk del curl

# Copies your code file from your action repository to the filesystem path `/` of the container
COPY entrypoint.sh /entrypoint.sh
RUN ["chmod", "+x", "/entrypoint.sh"]

# Code file to execute when the docker container starts up (`entrypoint.sh`)
ENTRYPOINT ["/entrypoint.sh"]