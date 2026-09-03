#!/bin/bash -e
usermod -aG dialout,video,tty,input ${FIRST_USER_NAME}
chown ${FIRST_USER_NAME}:${FIRST_USER_NAME} /home/${FIRST_USER_NAME}/.profile /home/${FIRST_USER_NAME}/.xinitrc
