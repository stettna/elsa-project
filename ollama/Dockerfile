FROM tensorflow/tensorflow:latest-gpu-jupyter

RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys A4B469963BF863CC

#ADD ./requirements.txt .

RUN apt-get update && apt-get install -y git
RUN apt-get install -y openssh-client
RUN apt-get install sudo
RUN apt-get install -y wget
RUN apt-get install -y pciutils
RUN apt-get install -y curl
RUN apt-get install zstd
RUN pip3 -q install pip --upgrade
RUN pip install --upgrade pip
RUN pip install crewai --ignore-installed

#RUN pip install -r requirements.txt

RUN curl -fsSL https://ollama.com/install.sh | sh

## Matching the cuda version for this container and T5 server Feb 2023
#RUN pip install --upgrade torch==1.12.1 --extra-index-url https://download.pytorch.org/whl/cu113
#RUN pip install --upgrade torch==1.13.1 --extra-index-url https://download.pytorch.org/whl/cu113 

RUN git config --global --add safe.directory /workspaces/elsa-project

EXPOSE 11434
