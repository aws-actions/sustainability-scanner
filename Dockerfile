# Container image that runs your code
FROM python:3.12-alpine

# Install required libs
RUN apk --no-cache add curl; \
    apk --no-cache add git; \
    apk --no-cache add bash

# Install CFN Guard (pinned release: the installer defaults to the latest release unless -v is given)
ARG CFN_GUARD_VERSION=3.2.1
RUN curl --proto '=https' --tlsv1.2 -sSf "https://raw.githubusercontent.com/aws-cloudformation/cloudformation-guard/${CFN_GUARD_VERSION}/install-guard.sh" | sh -s -- -v "${CFN_GUARD_VERSION}"
ENV PATH="/root/.guard/bin:${PATH}"

# Install AWS SusScan (pinned)
RUN pip3 install --no-cache-dir sustainability-scanner==1.3.0

# Uninstall libs
RUN apk del git; \
    apk del curl

# Copies your code files from your action repository to the filesystem path `/` of the container
COPY entrypoint.sh /entrypoint.sh
COPY report.py /report.py
RUN ["chmod", "+x", "/entrypoint.sh"]

# Code file to execute when the docker container starts up (`entrypoint.sh`)
ENTRYPOINT ["/entrypoint.sh"]