#!/usr/bin/env python3

import argparse
from pprint import pprint
import time
import os
import sys
import yaml
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
import msgpack


"""
@author: Jonathan Mickle
@summary: Traverses a through multi level dictionaries to diff them and return the changes -- Thanks to @tobywolf <https://github.com/tobywolf> for correcting logic
@param original: takes in the original unmodified JSON
@param modified: Takes in the modified json file for comparison
@return: a json dictionary of changes key-> value
"""
def diffDict(original, modified):
    if isinstance(original, dict) and isinstance(modified, dict):
        changes = {}
        for key, value in modified.items():
            if isinstance(value, dict):
                innerDict = diffDict(original[key], modified[key])
                if innerDict != {}:
                    changes[key] = {}
                    changes[key].update(innerDict)
            else:
                if key in original:
                    if value != original[key]:
                        changes[key] = value
                else:
                    changes[key] = value

        return changes
    else:
        raise Exception('parameters must be a dictionary')



def get_file_params(f):
    if os.path.exists(f):
        try:
            p = yaml.load(open(f, 'r'))
            return p
        except:
            return {}
    else:
        return {}


def parameter_update_serial(conn_fd, dtgm):
    import serial_datagram
    packer = msgpack.Packer(encoding='ascii', use_single_float=True)
    packet = serial_datagram.encode(packer.pack(dtgm))
    conn_fd.write(packet)
    print("update {} bytes: {}".format(len(packet), dtgm))


class FileChangeHandler(PatternMatchingEventHandler):
    def __init__(self, watch_dir, files, sendfn):
        PatternMatchingEventHandler.__init__(self, files)
        self.sendfn = sendfn
        self.param_file_contents = {}
        self.param_file_namespace = {}
        for f in files:
            self.param_file_namespace[f] = os.path.splitext(os.path.relpath(f, watch_dir))[0]
            self.param_file_contents[f] = get_file_params(f)
            self.sendfn({self.param_file_namespace[f]: self.param_file_contents[f]})

    def on_any_event(self, event):
        if event.event_type in ('modified', 'created') and not event.is_directory:
            print("---- event handler ----")
            # print(event.event_type)
            print(event.src_path)
            new_params = get_file_params(event.src_path)
            if new_params == {}:
                return
            # print(new_params)
            param_diff = diffDict(self.param_file_contents[event.src_path], new_params)
            if param_diff != {}:
                self.sendfn({self.param_file_namespace[event.src_path]: param_diff})
            # update parameter copy:
            self.param_file_contents[event.src_path] = new_params


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dir", help="parameter root directory to be watched")
    parser.add_argument("files", nargs='+', help="json parameter files to be watched")
    parser.add_argument("--uart", dest="uart", help="serial port device")
    parser.add_argument("--baud", dest="baudrate", default=921600, help="serial port baudrate")
    parser.add_argument("--tcp", dest="tcp", help="TCP/IP connection using cvra_rpc host:port")
    args = parser.parse_args()

    if args.uart != None:
        print("opening serial port {} with baud rate {}".format(args.uart, args.baudrate))
        import serial
        conn_fd = serial.Serial(args.uart, args.baudrate)
        sendfn = lambda dtgm : parameter_update_serial(conn_fd, dtgm)
    elif args.tcp != None:
        import cvra_rpc.service_call
        addr = str.split(args.tcp, ':')
        print("using tcp:", addr)
        sendfn = lambda dtgm : cvra_rpc.service_call.call(addr, 'parameter_set', [dtgm])
    else:
        print("please choose a connection protocol")
        exit(-1)

    files = [os.path.abspath(f) for f in args.files]
    watch_dir = os.path.abspath(args.dir)
    print("watching parameter files: {} in {}".format(
        [os.path.basename(f) for f in files], watch_dir))

    event_handler = FileChangeHandler(watch_dir, files, sendfn)
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
