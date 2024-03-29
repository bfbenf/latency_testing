from subprocess import check_output
from multiprocessing import Process, Queue
import re
import os
import time
from datetime import datetime
import boto3

RUN_TIME = 10800 ### NOTE - Time in seconds script is to run
START_TIME = time.time()
TARGET = "x.x.x.x"
NUMBER_OF_PINGS = 50
### MAC REGEX
"""
REGEX = re.compile(
    "(\d+) packets transmitted, (\d+) packets received, (\d+(?:.\d+)*)% packet loss\nround-trip min\/avg\/max\/stddev = (\d+.\d+)\/(\d+.\d+)\/(\d+.\d+)\/(\d+.\d+) ms"
)
"""
### Viking2
REGEX = re.compile("(\d+) packets transmitted, (\d+) received, (\d+(?:.\d+)*)% packet loss, time \d+ms\nrtt min\/avg\/max\/mdev = (\d+.\d+)\/(\d+.\d+)\/(\d+.\d+)\/(\d+.\d+) ms")
CLOUDWATCH = boto3.client(
    "cloudwatch",
    region_name="eu-west-2",
    aws_access_key_id=os.environ["access_key"],
    aws_secret_access_key=os.environ["secret_key"],
)
CLOUDWATCH_LOGS = boto3.client(
    "logs",
    region_name="eu-west-2",
    aws_access_key_id=os.environ["access_key"],
    aws_secret_access_key=os.environ["secret_key"],
)

def ping(q):
    start_time = time.time()
    output = check_output(
        "ping -f -c {qty} {address}".format(address=TARGET, qty=NUMBER_OF_PINGS),
        shell=True,
    ).decode("utf-8")
    q.put((output, start_time))


def upload(q, ping_result, stream_name):
    matches = re.findall(REGEX, ping_result[0])
    formatted_time = datetime.fromtimestamp(ping_result[1])
    CLOUDWATCH_LOGS.put_log_events(
        logGroupName="/wavelength/ping-data",
        logStreamName=stream_name,
        logEvents=[
            {"message": str(ping_result[0]), "timestamp": int(ping_result[1] * 1000)}
        ],
    )
    CLOUDWATCH.put_metric_data(
        Namespace="Wavelength",
        MetricData=[
            {
                "MetricName": "Average Round Trip Time",
                "Dimensions": [
                    {"Name": "target", "Value": TARGET},
                ],
                "Timestamp": formatted_time,
                "Value": float(matches[0][4]),
                "Unit": "Milliseconds",
                "StorageResolution": 1,
            },
            {
                "MetricName": "Minimum Round Trip Time",
                "Dimensions": [
                    {"Name": "target", "Value": TARGET},
                ],
                "Timestamp": formatted_time,
                "Value": float(matches[0][3]),
                "Unit": "Milliseconds",
                "StorageResolution": 1,
            },
            {
                "MetricName": "Maximum Round Trip Time",
                "Dimensions": [
                    {"Name": "target", "Value": TARGET},
                ],
                "Timestamp": formatted_time,
                "Value": float(matches[0][5]),
                "Unit": "Milliseconds",
                "StorageResolution": 1,
            },
            {
                "MetricName": "Standard Deviation Round Trip Time",
                "Dimensions": [
                    {"Name": "target", "Value": TARGET},
                ],
                "Timestamp": formatted_time,
                "Value": float(matches[0][6]),
                "Unit": "Milliseconds",
                "StorageResolution": 1,
            },
            {
                "MetricName": "Packets Transmitted",
                "Dimensions": [
                    {"Name": "target", "Value": TARGET},
                ],
                "Timestamp": formatted_time,
                "Value": float(matches[0][0]),
                "Unit": "Count",
                "StorageResolution": 1,
            },
            {
                "MetricName": "Packets Received",
                "Dimensions": [
                    {"Name": "target", "Value": TARGET},
                ],
                "Timestamp": formatted_time,
                "Value": float(matches[0][1]),
                "Unit": "Count",
                "StorageResolution": 1,
            },
            {
                "MetricName": "Packet Loss",
                "Dimensions": [
                    {"Name": "target", "Value": TARGET},
                ],
                "Timestamp": formatted_time,
                "Value": float(matches[0][2]),
                "Unit": "Percent",
                "StorageResolution": 1,
            }
        ],
    )


if __name__ == "__main__":
    ping_queue = Queue()
    upload_queue = Queue()
    stream_name = "ICMP_run_start_time_{time}".format(
        time=datetime.now().isoformat()
    ).replace(":", "_")
    CLOUDWATCH_LOGS.create_log_stream(
        logGroupName="/wavelength/ping-data", logStreamName=stream_name
    )
    while (time.time() - START_TIME) < RUN_TIME:
        pq = Process(target=ping, args=(ping_queue,))
        pq.start()
        ping_result = ping_queue.get()
        uq = Process(
            target=upload,
            args=(
                upload_queue,
                ping_result,
                stream_name,
            ),
        )
        uq.start()
    pq.join()
    uq.join()
