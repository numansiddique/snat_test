import sys
import time
import utils
from subprocess import call
from subprocess import check_output
from subprocess import CalledProcessError

from oslo.config import cfg
import neutron.agent.common.config as config


class SNatTest(object):
    DEV_NAME = 'snat_tst'
    DEV_PREFIX = 'snat_'
    
    def _init_vif(self, plugin):
        if plugin == 1:
            try:
                import neutron.agent.linux.interface as interface
                from neutron.agent.linux.interface import OVSInterfaceDriver
                conf = config.setup_conf()
                conf.register_opts(interface.OPTS)
                config.register_root_helper(conf)
                return OVSInterfaceDriver(conf)
            except:
                pass
        else:
            ROOT_HELPER_OPTS = [
                cfg.StrOpt('root_helper', default='sudo',
                           help=_('Root helper application.')),
                cfg.BoolOpt('ovs_use_veth', default=True,
                            help = _("ovs_use_veth")),
                cfg.StrOpt('ovs_integration_bridge',
                           default='br-int',
                           help=_('Name of Open vSwitch bridge to use'))
                            ]
            try:        
                from neutron_plugin_contrail.plugins.opencontrail.agent.contrail_vif_driver import ContrailInterfaceDriver
                contrail_conf = cfg.ConfigOpts()
                contrail_conf.register_opts(ROOT_HELPER_OPTS)
                contrail_conf.register_opts(ROOT_HELPER_OPTS, 'AGENT')
                return ContrailInterfaceDriver(contrail_conf)
            except:
                pass

        return None
    
    def read_config_file(self, file_name):
        with open(file_name, 'r') as f:
            for line in f:
                line = line.rstrip('\n')
                lst = line.split('=')
                if lst[0] == 'router':
                    self.router_id.append(lst[1])
                elif lst[0] == 'private':
                    newlst = lst[1].split(',')
                    priv_nw = {}
                    priv_nw['net'] = newlst[0]
                    priv_nw['subnet'] = newlst[1] 
                    self.private_ids.append(priv_nw)
                elif lst[0] == 'ext-network':
                    self.ext_nw_id.append(lst[1])
    
        if len(self.router_id) != 1:
            return False
        if len(self.private_ids) == 0:
            return False
        if len(self.ext_nw_id) != 1:
            return False
        return True
    
    def __init__(self):
        self._ns_index = 2
        self.router_id =[]
        self.private_ids = []
        self.ext_nw_id = []
        self.probe_data = {}
        self._vif_driver = self._init_vif(2)
        self._total_tests = 0
        self._total_failures = 0
        self._total_success= 0
        self._debug = 1
        self._port_dhcp = True
        
    def add_interface_to_router(self, router_id, subnet_id):
        cmd = ['neutron', 'router-interface-add',router_id, subnet_id]
        utils.execute(cmd)
        # time.sleep(2)

    def delete_interface_from_router(self, router_id, subnet_id):
        cmd = ['neutron', 'router-interface-delete',router_id, subnet_id]
        utils.execute(cmd)
        # time.sleep(2)

    def set_gw_to_router(self, router_id, ext_network_id):
        cmd = ['neutron', 'router-gateway-set',router_id, ext_network_id]   
        utils.execute(cmd)
        # time.sleep(2)

    def clear_gw_to_router(self, router_id):
        cmd = ['neutron', 'router-gateway-clear',router_id]
        utils.execute(cmd)
    # time.sleep(2)

    def list_router(self, router_id):
        if self._debug:
            cmd = ['neutron', 'router-list']
            call(cmd)
            
            cmd = ['neutron', 'router-show', router_id]
            call(cmd)
            
            cmd = ['neutron', 'router-port-list', router_id]
            call(cmd)
            
            cmd = ['sudo', 'ip', 'netns']
            call(cmd)
     
    def _extract_port_data(self, port_buffer):
        # extract the port_id
        id_index = port_buffer.find('| id')
        port_buffer = port_buffer[id_index+4:]
        id_index = port_buffer.find('| ')
        end_index = port_buffer.find('|', id_index + 1)
        port_id = port_buffer[id_index+1:end_index]
        port_id = port_id.strip(' ')
        port_buffer = port_buffer[end_index:]
        
        # extract the mac address
        id_index = port_buffer.find('mac_address')
        port_buffer = port_buffer[id_index+11:]
        id_index = port_buffer.find('| ')
        end_index = port_buffer.find('|', id_index + 1)
        mac_id = port_buffer[id_index+1:end_index]
        mac_id = mac_id.strip(' ')
        return port_id, mac_id 

    def _extract_gw_ip(self, subnet_buffer):
        id_index = subnet_buffer.find('gateway_ip')
        subnet_buffer = subnet_buffer[id_index+10:]
        id_index = subnet_buffer.find('| ')
        end_index = subnet_buffer.find('|', id_index + 1)
        gw_ip = subnet_buffer[id_index+1:end_index]
        gw_ip = gw_ip.strip(' ')
        return gw_ip
              
    def create_probe_port(self, network):
        # create a port
        network_id = network['net']
        print "In function create_probe_port\n Creating a probe port"
        cmd = ['neutron', 'port-create', network_id]
        port_output = check_output(cmd)
        port_id, mac_id = self._extract_port_data(port_output)
        
        dev_name = '%s%s' %(SNatTest.DEV_NAME, self._ns_index)
        namespace = '%s%s' %(dev_name, self._ns_index)
        self._ns_index += 1
        
        cmd = ['neutron', 'subnet-show', network['subnet']]
        subnet_output = check_output(cmd)
        gw_ip = self._extract_gw_ip(subnet_output)
        
        try:
            msg = "Plugging the port " +  dev_name + " with namespace " + namespace + " to the VIF driver..\n"
            print msg
            self._vif_driver.plug(network_id, port_id, dev_name, mac_id, 
                        namespace=namespace, prefix=SNatTest.DEV_PREFIX)
            
            # configure ip address for the port
            if self._port_dhcp:
                cmd = ['sudo','ip', 'netns', 'exec', namespace, 'dhclient', dev_name]
                utils.execute(cmd)
                cmd = ['sudo','ip', 'netns', 'exec', namespace, 'ifconfig']
                output = check_output(cmd)
                print "output of ifconfig is \n"
                print output + "\n"
                time.sleep(10)
                
        except Exception as e:
            print "Exception in vif plug : ", e
            
        port_info = {}
        port_info['port_id'] = port_id
        port_info['mac_id'] = mac_id
        port_info['dev_name'] = dev_name
        port_info['namespace'] = namespace
        port_info['gateway'] = gw_ip
        self.probe_data[network_id] = port_info
    

    def delete_probe_port(self, network_id):
        if network_id not in self.probe_data:
            return
        port_info = self.probe_data[network_id]
        # unplug the interface
        self._vif_driver.unplug(port_info['dev_name'], namespace=port_info['namespace'], 
                          prefix=self.DEV_PREFIX)
        
        cmd = ['neutron', 'port-delete', port_info['port_id']]
        utils.execute(cmd)
        
        cmd = ['sudo', 'ip', 'netns', 'delete', port_info['namespace'] ]
        utils.execute(cmd)        

    
        def create_router(self, name):
            pass


    
    def test_snat(self):
        for private_id in self.private_ids:
            print "Creating the probe ports\n"
            self.create_probe_port(private_id)
            
        for private_id in self.private_ids:
            self._test_ping(private_id['net'], True)
        
        # clear router gateway and test
        self.clear_gw_to_router(self.router_id[0])
        
        # now test the connectivity.
        print "Cleared the Gateway and testing"
        for private_id in self.private_ids:
            self._test_ping(private_id['net'], False)
            
        #set the gateway back and test again
        self.set_gw_to_router(self.router_id[0], self.ext_nw_id[0])
        print "Gateway set again and testing"
        for private_id in self.private_ids:
            self._test_ping(private_id['net'], True)
            
        print "Deleting the interfaces from the router and testing"
        for private_id in self.private_ids:
            print "Deleting the interface from the router for the network : " + str(private_id['net']) +"\n"
            self.delete_interface_from_router(self.router_id[0], private_id['subnet'])
            self._test_ping(private_id['net'], False)
            
            # add the interface back and test again
            print "Adding the interface back to the router for the network : " + str(private_id['net']) +"\n"
            self.add_interface_to_router(self.router_id[0], private_id['subnet'])
            self._test_ping(private_id['net'], True)
            
            
    def clean_up(self):
        self.list_router(self.router_id[0])
        # clear the gateway
        try:
            self.clear_gw_to_router(self.router_id[0])
        except:
            pass
        
        # delete the ports of the router
        for private_nw in self.private_ids:
            try:
                self.delete_interface_from_router(self.router_id[0], private_nw['subnet'])
            except:
                pass
            try:
                self.delete_probe_port(private_nw['net'])
            except:
                pass
    
        self.list_router(self.router_id[0])

 
    def setup_router(self):
        for private_nw in self.private_ids:
            self.add_interface_to_router(self.router_id[0], private_nw['subnet'])
            
        # add the gw to the router
        self.set_gw_to_router(self.router_id[0], self.ext_nw_id[0])
   
    def _ping_address(self,port_info, address):
        try:
            
            cmd = ['sudo', 'ip', 'netns', 'exec', port_info['namespace'], 'ping', '-c3', address]
            print "Executing the ping command\n"
            ping_output = check_output(cmd)
            print "ping_output = " , ping_output
        except:
            ping_output = ""
        
        if ping_output.find('icmp_seq=') == -1:
            print "ping to the address [%s] failed for the port %s:%s " \
                    %(address, port_info['namespace'], port_info['dev_name'])
            return False
                                                      
        else:
            print "ping to the address [%s] Success for the port %s:%s " \
                    %(address, port_info['namespace'], port_info['dev_name'])
            return True
            
    def _test_ping(self, network_id, success):
        print "In function test_ping for the network :" + str(network_id) + "\n"
        if network_id not in self.probe_data:
            return
        
        port_info = self.probe_data[network_id]
        # ping gateway address
        self._total_tests += 1
        print "Pinging to the Gateway : " + port_info['gateway'] + "\n"
        result = self._ping_address(port_info, port_info['gateway'])
        if result:
            self._total_success += 1
        else:
            self._total_failures += 1
            
        print "Pinging to 173.194.34.147 --> www.google.com"
        self._total_tests += 1
        result = self._ping_address(port_info, '173.194.34.147')
        if result:
            if success:
                print "Test to 173.194.34.147 passed as expected"
                self._total_success += 1
            else:
                print "Test to 173.194.34.147 FAILED"
                self._total_failures += 1
        else:
            if success:
                print "Test to 173.194.34.147 FAILED"
                self._total_failures += 1
            else:
                print "Test to 173.194.34.147 passed as expected"
                self._total_success += 1
            
        print "Pinging to www.google.com"
        self._total_tests += 1
        result = self._ping_address(port_info, 'www.google.com')
        if result:
            if success:
                print "Test to www.google.com passed as expected"
                self._total_success += 1
            else:
                print "Test to www.google.com FAILED"
                self._total_failures += 1
        else:
            if success:
                print "Test to www.google.com FAILED"
                self._total_failures += 1
            else:
                print "Test to www.google.com passed as expected"
                self._total_success += 1
            
        print "Ping test completed for the private network : " + str(network_id) + "\n"
        
    def display_test_summary(self):
        print "\n----------SNAT Test summary-----------------\n"
        print "Total Tests = ", self._total_tests
        print "Total Success = ", self._total_success
        print "Total Failures = ", self._total_failures
        print "\n----------SNAT Test summary End-----------------\n"
    

def main(argv=sys.argv[1:]):
    snat_test = SNatTest()
    if not snat_test._vif_driver:
        print "VIF driver is None"
        return

    if not snat_test.read_config_file('snat_test.ini'):
        print "Invalid snat_test.ini"
        print "Define router_id, interface_id and ext_nw_id correctly"
        return
    
    #clean up
    try:
        print "\nWelcome to the SNAT test...\n"
        #print "\nCleaning up before setting up\n"
        #snat_test.clean_up()
        
        # setup the router
        print "Setting up the router..\n"
        snat_test.setup_router()
        # now test various scenarios
        
        print "Starting the snat tests\n"
        snat_test.test_snat()    
        
        #clean up
        print "Tests finished, cleaning up..\n"
        snat_test.clean_up()
    except Exception as e:
        print "\nException occured : ", e
        snat_test.clean_up()
    
    print "\nExiting the snat test utility\n"
    #show the test result summary
    snat_test.display_test_summary()

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
