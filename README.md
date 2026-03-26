# cml_device_mgmt_config
Automate Configuring Management IP config on CML nodes for reachability

## steps:

1. create lab in your cml, this will also create default cisco/cisco username and password credentials.
2. update the hosts.json based on your node names and assign ip addresses to be configured.
3. update .env with required info
4. run "python3 apply_cml_lab_nodes.py"

### note:
currently works on ios_xr (xrv9k) and ios_xe (cat8000v, csr1000v) platforms.
