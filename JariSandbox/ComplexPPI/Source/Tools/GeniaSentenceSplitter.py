__version__ = "$Revision: 1.1 $"

import sys,os
import sys
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import cElementTree as ET
import cElementTreeUtils as ETUtils

import shutil
import subprocess
import tempfile
import codecs
"""
A wrapper for the Joachims SVM Multiclass classifier.
"""

sentenceSplitterDir = "/home/jari/biotext/tools/geniass"

def makeSentences(input, output=None, removeText=False):
    global sentenceSplitterDir
    
    print >> sys.stderr, "Loading corpus", input
    corpusTree = ETUtils.ETFromObj(input)
    print >> sys.stderr, "Corpus file loaded"
    corpusRoot = corpusTree.getroot()
    
    docCount = 0
    for document in corpusRoot.findall("document"):
        docId = document.get("id")
        if docId == None:
            docId = "CORPUS.d" + str(docCount)
        assert document.find("sentence") == None
        text = document.get("text")
        assert text != None
        # Write text to workfile
        workdir = tempfile.mkdtemp()
        workfile = codecs.open(os.path.join(workdir, "sentence-splitter-input.txt"), "wt", "utf-8")
        workfile.write(text)
        workfile.close()
        # Run sentence splitter
        args = [sentenceSplitterDir + "/run_geniass.sh", os.path.join(workdir, "sentence-splitter-input.txt"), os.path.join(workdir, "sentence-splitter-output.txt")]
        subprocess.call(args)
        # Read split sentences
        workfile = codecs.open(os.path.join(workdir, "sentence-splitter-output.txt"), "rt", "utf-8")
        start = 0
        sentenceCount = 0
        for sText in workfile.readlines():
            sText = sText.strip()
            cStart = text.find(sText, start)
            cEnd = cStart + len(sText)
            start = cStart + len(sText)
            # make sentence element
            e = ET.Element("sentence")
            e.set("text", sText)
            e.set("charOffset", str(cStart) + "-" + str(cEnd - 1)) # NOTE: check
            e.set("id", docId + ".s" + str(sentenceCount))
            document.append(e)
            sentenceCount += 1
        # Remove original text
        if removeText:
            del document["text"]
        # Remove work directory
        shutil.rmtree(workdir)
        docCount += 1
        
    if output != None:
        print >> sys.stderr, "Writing output to", output
        ETUtils.write(corpusRoot, output)
    return corpusTree
    
if __name__=="__main__":
    import sys
    
    from optparse import OptionParser
    # Import Psyco if available
    try:
        import psyco
        psyco.full()
        print >> sys.stderr, "Found Psyco, using"
    except ImportError:
        print >> sys.stderr, "Psyco not installed"

    optparser = OptionParser(usage="%prog [options]\n")
    optparser.add_option("-i", "--input", default=None, dest="input", help="Corpus in interaction xml format", metavar="FILE")
    optparser.add_option("-o", "--output", default=None, dest="output", help="Output file in interaction xml format.")
    (options, args) = optparser.parse_args()
    
    makeSentences(input=options.input, output=options.output, removeText=False)
    