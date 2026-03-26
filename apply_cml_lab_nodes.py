from cml_utils import *

if __name__ == "__main__":
    
    instance = CML(cml_ip, cml_user, cml_password)
    token=instance.get_token()
    labname, labid=instance.get_lab(my_lab, token)

    nodes = instance.get_nodes(labid, token)
    mapped_nodes=instance.get_ip_mapped_nodes(nodes)
    print(mapped_nodes)
    #instance.config_management(token, labid, mapped_nodes)
    instance.config_management_via_client(labname, mapped_nodes)

    del instance