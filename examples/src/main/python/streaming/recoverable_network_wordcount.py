#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
 Counts words in text encoded with UTF8 received from the network every second.

 Usage: recoverable_network_wordcount.py <hostname> <port> <checkpoint-directory> <output-file>
   <hostname> and <port> describe the TCP server that Spark Streaming would connect to receive
   data. <checkpoint-directory> directory to HDFS-compatible file system which checkpoint data
   <output-file> file to which the word counts will be appended

 To run this on your local machine, you need to first run a Netcat server
    `$ nc -lk 9999`

 and then run the example
    `$ bin/spark-submit examples/src/main/python/streaming/recoverable_network_wordcount.py \
        localhost 9999 ~/checkpoint/ ~/out`

 If the directory ~/checkpoint/ does not exist (e.g. running for the first time), it will create
 a new StreamingContext (will print "Creating new context" to the console). Otherwise, if
 checkpoint data exists in ~/checkpoint/, then it will create StreamingContext from
 the checkpoint data.
"""
import os
import sys

from pyspark import SparkContext
from pyspark.streaming import StreamingContext


# Get or register a Broadcast variable
def getWordExcludeList(sparkContext):
    if ('wordExcludeList' not in globals()):
        globals()['wordExcludeList'] = sparkContext.broadcast(["a", "b", "c"])
    return globals()['wordExcludeList']


# Get or register an Accumulator
def getDroppedWordsCounter(sparkContext):
    if ('droppedWordsCounter' not in globals()):
        globals()['droppedWordsCounter'] = sparkContext.accumulator(0)
    return globals()['droppedWordsCounter']


def createContext(host, port, outputPath):
    # If you do not see this printed, that means the StreamingContext has been loaded
    # from the new checkpoint
    print("Creating new context")
    if os.path.exists(outputPath):
        os.remove(outputPath)
    sc = SparkContext(appName="PythonStreamingRecoverableNetworkWordCount")
    ssc = StreamingContext(sc, 1)

    # Create a socket stream on target ip:port and count the
    # words in input stream of \n delimited text (e.g. generated by 'nc')
    lines = ssc.socketTextStream(host, port)
    words = lines.flatMap(lambda line: line.split(" "))
    wordCounts = words.map(lambda x: (x, 1)).reduceByKey(lambda x, y: x + y)

    def echo(time, rdd):
        # Get or register the excludeList Broadcast
        excludeList = getWordExcludeList(rdd.context)
        # Get or register the droppedWordsCounter Accumulator
        droppedWordsCounter = getDroppedWordsCounter(rdd.context)

        # Use excludeList to drop words and use droppedWordsCounter to count them
        def filterFunc(wordCount):
            if wordCount[0] not in excludeList.value:
                return True
            droppedWordsCounter.add(wordCount[1])
            return False

        counts = "Counts at time %s %s" % (time, rdd.filter(filterFunc).collect())
        print(counts)
        print("Dropped %d word(s) totally" % droppedWordsCounter.value)
        print("Appending to " + os.path.abspath(outputPath))
        with open(outputPath, 'a') as f:
            f.write(counts + "\n")

    wordCounts.foreachRDD(echo)
    return ssc

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: recoverable_network_wordcount.py <hostname> <port> "
              "<checkpoint-directory> <output-file>", file=sys.stderr)
        sys.exit(-1)
    host, port, checkpoint, output = sys.argv[1:]
    ssc = StreamingContext.getOrCreate(checkpoint,
                                       lambda: createContext(host, int(port), output))
    ssc.start()
    ssc.awaitTermination()
