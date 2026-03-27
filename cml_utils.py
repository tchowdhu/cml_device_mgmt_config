import requests, getpass, ipaddress, os
from jinja2 import Environment, FileSystemLoader
import urllib3, pprint, json
from dotenv import load_dotenv
from virl2_client import ClientLibrary
import time
import paramiko

# Disable SSL warnings (since you're using HTTPS with likely self-signed cert)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

'''
cml_ip = ipaddress.ip_address(input("Enter CML IP address: "))
cml_user = str(input("Enter CML username: "))
cml_password = str(getpass.getpass("Enter Password: "))
'''

cml_ip=str(os.getenv("CML_IP"))
cml_user=str(os.getenv("CML_USER"))
cml_password=str(os.getenv("CML_PASS"))
my_lab=str(os.getenv("CML_LAB"))
host_file=str(os.getenv("CML_NODES_FILE"))
device_user=str(os.getenv("DEV_USER"))
device_password=str(os.getenv("DEV_PASS"))
snmp_ro=str(os.getenv("SNMP_RO"))
snmp_rw=str(os.getenv("SNMP_RW"))

class CML:
    def __init__(self, cml_ip, cml_user, cml_password):
        self.cml_ip = cml_ip
        self.base_url = "https://{}".format(cml_ip)
        self.base_api_url = "https://{}/api/v0/".format(cml_ip)
        self.authenticate_url = self.base_api_url+"authenticate"
        self.all_labs_url=self.base_api_url+"labs?show_all=true"
        self.labs_url=self.base_api_url+"labs/"
        self.mylab_url=None
        self.mynodes_url=None

    def get_token(self):
        access_info = {
            "username": cml_user,
            "password": cml_password
        }
        header = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        response = requests.post(
            url=self.authenticate_url, 
            headers=header,  
            json=access_info, 
            verify=False
        )

        token = response.json()
        response.close()
        
        return token
    
    def get_lab(self, lab_name, token):
        header = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(token)
        }
        response = requests.get(
            url=self.all_labs_url, 
            headers=header,  
            data={}, 
            verify=False
        )

        labs=response.json()
        response.close()
        
        for lab in labs:
            check_lab = requests.get (
                url=self.labs_url+lab,
                headers=header,
                data={},
                verify=False
            )

            if check_lab.json()['lab_title'] == lab_name:
                check_lab.close()
                self.mylab_url=self.labs_url+lab+"/"
                self.mynodes_url=self.mylab_url+"nodes?data=true&exclude_configurations=true"
                return lab_name, lab
            else:
                check_lab.close()

        return ()

    def get_nodes(self, lab_id, token):
        header = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(token)
        }
        response = requests.get(
            url=self.mynodes_url, 
            headers=header,  
            data={}, 
            verify=False
        )
        nodes = response.json()
        response.close()

        core_nodes=[]
        cpe_nodes=[]
        
        for node in nodes:
            if node["node_definition"] == "iosxrv9000":
                core_nodes.append(
                    {
                        "id": node["id"],
                        "label": node["label"],
                        "type": "ios_xr"
                    }
                )
            elif (node["node_definition"] == "cat8000v") or (node["node_definition"] == "csr1000v"):
                cpe_nodes.append(
                    {
                        "id": node["id"],
                        "label": node["label"],
                        "type": "ios_xe"
                    }
                )
        cisco_nodes=core_nodes.copy()
        cisco_nodes.extend(cpe_nodes)

        return cisco_nodes

    def get_ip_mapped_nodes(self, node_list):
        
        with open(host_file, "r") as f:
            ip_list=json.load(f)

        # Create a dictionary from ip_list for quick lookup by label
        ip_map = {}
        for item in ip_list:
            for label, ip in item.items():
                ip_map[label] = ip

        # Map node_list entries with their corresponding IP addresses
        mapped_nodes = []
        for node in node_list:
            label = node['label']
            ip_address = ip_map.get(label)
            if ip_address:
                mapped_node = {
                    'id': node['id'],
                    'label': label,
                    'type': node['type'],
                    'ip_address': ip_address
                }
                mapped_nodes.append(mapped_node)

        return mapped_nodes

    def config_management(self, token, labid, node_list):
        env = Environment(loader=FileSystemLoader('./templates'))  # Adjust path as needed
        template_xr = env.get_template('xr_basic_config.j2')
        template_xe = env.get_template('xe_basic_config.j2')

        header = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(token)
        }

        for node in node_list:
            cidr = node['ip_address']

            # Parse network and extract details
            network = ipaddress.ip_network(cidr, strict=False)
            ip_address = str(ipaddress.ip_interface(cidr).ip)
            netmask = str(network.netmask)
            gateway = str(next(network.hosts()))

            # Jinja template variables
            template_vars = {
                "management_ip": ip_address,
                "mask": netmask,
                "gateway": gateway,
                "readonly_com": snmp_ro,
                "readwrite_com": snmp_rw
            }
            rendered_config=None
            if node['type'] == 'ios_xr':
                rendered_config = template_xr.render(template_vars)
            elif node['type'] == 'ios_xe':
                rendered_config = template_xe.render(template_vars)

            print(rendered_config)
            payload = {
                "configuration": rendered_config
            }

            url = self.labs_url+"{}/nodes/{}".format(labid, node['id'])

            response = requests.patch(url, headers=header, json=payload, verify=False)

            print(response.json())

            response.close()

    def config_management_via_client(self, labname, node_list):
        CONSOLE_LINE=0
        env = Environment(loader=FileSystemLoader('./templates'))  # Adjust path as needed
        template_xr = env.get_template('xr_basic_config.j2')
        template_xe = env.get_template('xe_basic_config.j2')

        for node in node_list:
            cidr = node['ip_address']

            # Parse network and extract details
            network = ipaddress.ip_network(cidr, strict=False)
            ip_address = str(ipaddress.ip_interface(cidr).ip)
            netmask = str(network.netmask)
            gateway = str(next(network.hosts()))

            # Jinja template variables
            template_vars = {
                "management_ip": ip_address,
                "mask": netmask,
                "gateway": gateway,
                "readonly_com": snmp_ro,
                "readwrite_com": snmp_rw
            }
            rendered_config=None
            if node['type'] == 'ios_xr':
                rendered_config = template_xr.render(template_vars)
                rendered_config = "configure\n"+rendered_config+"\ncommit\nend\n"
            elif node['type'] == 'ios_xe':
                rendered_config = template_xe.render(template_vars)
                rendered_config = "configure terminal\n"+rendered_config+"\nend\nwrite memory\n"

            print(rendered_config)
            
            console_path = f"/{labname}/{node['label']}/{CONSOLE_LINE}"
            remote_cmd = f'open {console_path}'
            
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=self.cml_ip,
                username=cml_user,
                password=cml_password,
                look_for_keys=False,
                allow_agent=False,
            )

            chan = ssh.invoke_shell()
            time.sleep(1)
            chan.recv(65535)

            # enter the CML console server command
            chan.send(remote_cmd + "\n")
            time.sleep(3)

            output = chan.recv(65535).decode(errors="ignore")
            print(output)
            
            # Wake up the device console
            chan.send("\n")
            time.sleep(2)
            buf = chan.recv(65535).decode(errors="ignore")
            print(buf)
            
            # Device login
            if "Username" in buf or "login" in buf:
                chan.send(device_user + "\n")
                time.sleep(1)
                buf = chan.recv(65535).decode(errors="ignore")
                print(buf)

            if "Password" in buf:
                chan.send(device_password + "\n")
                time.sleep(2)
                buf = chan.recv(65535).decode(errors="ignore")
                print(buf)
                
            if node['type']=='ios_xe':
                chan.send("enable\n")
                time.sleep(2)
                if "Password" in buf:
                    chan.send(device_password + "\n")
                    time.sleep(2)
                    buf = chan.recv(65535).decode(errors="ignore")
                    print(buf)
                    
            for cmd in rendered_config.split('\n'):
                chan.send(cmd + "\n")
                time.sleep(2)
                data = chan.recv(65535).decode(errors="ignore")
                print(data)
                

                

            # disconnect from node console back to CML console server
            chan.send("\x1d")   # Ctrl-]
            time.sleep(1)

            ssh.close()

