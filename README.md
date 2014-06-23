snat_test
=========

Contrail SNAT Test

Please follow the below steps
1. Take the latest R1.06 contrail-neutron-plugin repo
2. Got to the directory /opt/stack/contrail/controller/src/vnsw/contrail-vrouter-api/
   a. cd /opt/stack/contrail/controller/src/vnsw/contrail-vrouter-api/
   b. Edit the file contrail_vrouter_api/vrouter_api.py and modify the line number 7 to below 
     from nova_contrail_vif.gen_py.instance_service import InstanceService, ttype
   c. Install contrail_vrouter_api package. python setup.py build, sudo python setup.py install

3. Clone this repo and add the file snat_test.ini and add the below lines

router=<ROUTER_ID>
private=<PRIVATE_NET_ID>,<PRIV_SUBNET_ID>
ext-network=<EXT_NETWORK_ID>

Below is one example

router=de4badc6-5b73-4400-aa8b-dda18648c2e7
private=f32a9d11-c53f-41ec-9c6e-122f55b12eda,1829f145-b920-4d4e-8c3a-a93f57404a3b
ext-network=2c3cb54a-5074-4f5e-b6a5-8a1e3450eb69

4. Run snat_test.py --> python snat_test.py


