# LFHCAL CAEN Monitoring

## Instructions
1) Source the conda init script with `source ~/.conda_init.sh`.  **NOTE:** This must be done in a different shell than JANUS is started from.  JANUS and the online monitoring depende on different versions of Python.
2) To access from another computers, open an ssh tunnel to the host computer with `ssh -L 54321:localhost:54321 ...`
3) From a web broweser, go to `localhost:54321`.  All the monitoring plots shoudl be available from here.
