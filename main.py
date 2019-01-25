from kubernetes import config, client, watch
from kubernetes.client.rest import ApiException
import os
import subprocess
import boto3
import logging

def get_token(cluster_name):
    args = ("/usr/local/bin/aws-iam-authenticator", "token", "-i", cluster_name, "--token-only")
    popen = subprocess.Popen(args, stdout=subprocess.PIPE)
    popen.wait()
    return popen.stdout.read().rstrip()

def get_subnet_az(subnet_id):
    ec2 = boto3.resource('ec2', region_name=os.getenv('AWS_REGION'))
    subnet = ec2.Subnet(subnet_id)
    logging.info("The subnet is in AZ %s", subnet.availability_zone)
    return subnet.availability_zone

def get_instance_az(external_id):
    ec2 = boto3.client('ec2', region_name=os.getenv('AWS_REGION'))
    instance_az = ec2.describe_instances(InstanceIds=[external_id])['Reservations'][0]['Instances'][0]['Placement']['AvailabilityZone']
    logging.info("The instance is in AZ %s", instance_az)
    return instance_az

def find_eniconfig(instance_az):
    api_instance = client.CustomObjectsApi(client.ApiClient())
    try:
        eniconfigs = api_instance.list_cluster_custom_object(group='crd.k8s.amazonaws.com', version='v1alpha1', plural='eniconfigs')
        logging.info("Dictionary of ENIConfigs: %s", eniconfigs)
        for eniconfig in eniconfigs['items']:
            if get_subnet_az(eniconfig['spec']['subnet']) == instance_az:
                body = {
                    "metadata": {
                        "annotations": {
                            "k8s.amazonaws.com/eniConfig": eniconfig['metadata']['name']
                        }
                    }
                }
                return body
    except ApiException as e:
        logging.error(e)

#api_token = get_token("han")
#configuration = client.Configuration()
#configuration.host = 'https://9685B319BF77EF70E801FEB00983EF41.yl4.us-west-2.eks.amazonaws.com'
#configuration.debug = False
#configuration.api_key['authorization']= "Bearer " + api_token
#configuration.assert_hostname = True
#configuration.verify_ssl = False
#client.Configuration.set_default(configuration)

config.load_incluster_config()
v1 = client.CoreV1Api()
logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)

w = watch.Watch()
for item in w.stream(v1.list_node, timeout_seconds=0):
    node = item['object']
    if item['type'] == 'ADDED':
        external_id = node.spec.external_id
        instance_az = get_instance_az(external_id)
        body = find_eniconfig(instance_az)
        if body != None:
            v1.patch_node(node.metadata.name,body)

