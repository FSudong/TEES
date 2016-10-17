import sys,os
import re
import zipfile
import shutil
thisPath = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(thisPath,"../../")))
try:
    import cElementTree as ET
except ImportError:
    import xml.etree.cElementTree as ET
import Utils.ElementTreeUtils as ETUtils
import Utils.InteractionXML.MakeSets as MakeSets
from Detectors.Preprocessor import Preprocessor
import Utils.Stream as Stream

class Sentence():
    def __init__(self, origId, text, corpusId, usedIds, setName):
        self.origId = origId
        self.corpusId = corpusId
        self.id = corpusId + ".d" + origId + ".s" + origId
        assert self.id not in usedIds
        usedIds.add(self.id)
        self.text = text
        self.entities = []
        self.relation = None
        self.comment = None
        self.setName = setName
    
    def process(self, directed, negatives):
        # Build the entities
        for tag in ("e1", "e2"):
            self.entities.append(self._getEntity(self.text, tag))
            self.text = self.text.replace("<" + tag + ">", "").replace("</" + tag + ">", "")
        # Check entity offsets
        for entity in self.entities:
            begin, end = [int(x) for x in entity.get("charOffset").split("-")]
            assert entity.get("text") == self.text[begin:end], (entity.get("text"), self.text, self.text[begin:end], [begin, end])
        assert len(self.entities) == 2
        eMap = {"e1":self.entities[0], "e2":self.entities[1]}
        for key in eMap:
            assert eMap[key].get("id").endswith("." + key)
        # Build the sentence
        docElem = ET.Element("document", {"id":self.corpusId + ".d" + self.origId, "set":self.setName})
        sentElem = ET.SubElement(docElem, "sentence", {"id":self.id, "charOffset":"0-"+str(len(self.text)), "text":self.text})
        if self.comment != None and self.comment != "":
            sentElem.set("comment", self.comment)
        for entity in self.entities:
            sentElem.append(entity)
        # Determine interaction types per direction
        relFrom, relTo = "", ""
        if self.relation == "Other":
            forwardType = "Other"
            reverseType = "Other"
        else:
            relType, rest = self.relation.strip(")").split("(")
            relFrom, relTo = rest.split(",")
            if relFrom == "e1":
                assert relTo == "e2"
                forwardType = relType
                reverseType = "neg"
            else:
                assert relFrom == "e2" and relTo == "e1"
                forwardType = "neg"
                reverseType = relType
        # Build the interactions
        if directed:
            if negatives or (forwardType != "neg"):
                sentElem.append(self._getInteraction(forwardType, "e1", "e2", directed, 0, eMap, "e1", "e2"))
            if negatives or (reverseType != "neg"):
                sentElem.append(self._getInteraction(reverseType, "e2", "e1", directed, 1, eMap, "e2", "e1"))
        else:
            sentElem.append(self._getInteraction(self.relation, "e1", "e2", directed, 0, eMap, relFrom, relTo))
        return docElem
    
    def _getInteraction(self, relType, e1, e2, directed, count, eMap, relFrom=None, relTo=None):
        if relFrom == None: relFrom = e1
        if relTo == None: relFrom = e2
        attrs = {"id":self.id + ".i" + str(count), "type":relType, "directed":str(directed), "e1":eMap[e1].get("id"), "e2":eMap[e2].get("id")}
        if relFrom != "": attrs["from"] = relFrom
        if relTo != "": attrs["to"] = relTo
        return ET.Element("interaction", attrs)
    
    def _getEntity(self, line, tag):
        try:
            before, entityText, after = re.split(r'<' + tag + '>|</' + tag + '>', line)
        except ValueError as e:
            print "ValueError in line '" + line + "' for tag", tag
            raise e
        begin = len(before)
        end = len(before) + len(entityText)
        return ET.Element("entity", {"text":entityText, "type":"entity", "charOffset":str(begin)+"-"+str(end), "id":self.id + "." + tag})
        
def processLines(lines, setName, usedIds, directed=True, negatives=False, tree=None, corpusId="SE10T8"):
    if tree == None:
        corpus = ET.Element("corpus", {"source":corpusId})
        tree = ET.ElementTree(corpus)
    else:
        corpus = tree.getroot()
    sentence = None
    for line in lines:
        line = line.strip()
        if sentence == None:
            assert line[0].isdigit(), line
            origId, line = line.split("\t")
            sentence = Sentence(origId, line.strip().strip("\""), corpusId, usedIds, setName)
        else:
            if line.startswith("Comment:"):
                sentence.comment = line.split(":", 1)[-1].strip()
            elif line != "":
                sentence.relation = line
            else:
                assert sentence != None
                corpus.append(sentence.process(directed=directed, negatives=negatives))
                sentence = None
    return tree

def convert(inPath, outDir, corpusId, directed, negatives, preprocess, debug=False, clear=False, constParser="BLLIP-BIO", depParser="STANFORD-CONVERT"):
    # Prepare the output directory
    if not os.path.exists(outDir):
        print "Making output directory", outDir
        os.makedirs(outDir)
    elif clear:
        print "Removing output directory", outDir
        for filename in os.listdir(outDir):
            if filename != "log.txt":
                os.remove(os.path.join(outDir, filename))
    # Read and process the corpus files
    archive = zipfile.ZipFile(inPath, 'r')
    usedIds = set()
    tree = None
    for fileName, setName in [("SemEval2010_task8_all_data/SemEval2010_task8_training/TRAIN_FILE.TXT", "train"),\
                              ("SemEval2010_task8_all_data/SemEval2010_task8_testing_keys/TEST_FILE_FULL.TXT", "test")]:
        print "Processing file", fileName, "as set", setName
        f = archive.open(fileName)
        tree = processLines(f.readlines(), setName, directed=directed, negatives=negatives, usedIds=usedIds, tree=tree, corpusId=corpusId)
        f.close()
    # Divide the training set into training and development sets
    MakeSets.processCorpus(tree, None, "train", [("train", 0.7), ("devel", 1.0)], 1)
    # Write out the converted corpus
    convertedPath = os.path.join(outDir, "SemEval2010Task8-converted.xml")
    ETUtils.write(tree.getroot(), convertedPath)
    # Preprocess the converted corpus
    if preprocess:
        outPath = os.path.join(outDir, "SemEval2010Task8.xml")
        preprocessor = Preprocessor(constParser, depParser)
        preprocessor.setArgForAllSteps("debug", debug)
        preprocessor.stepArgs("CONVERT")["corpusName"] = corpusId
        preprocessor.process(convertedPath, outPath, omitSteps=["SPLIT-SENTENCES", "NER", "SPLIT-NAMES"])

if __name__=="__main__":
    from optparse import OptionParser
    optparser = OptionParser(usage="%prog [options]\n")
    optparser.add_option("-i", "--input", default=None)
    optparser.add_option("-o", "--outdir", default=None, dest="outdir", help="directory for output files")
    optparser.add_option("-r", "--directed", default=False, action="store_true", help="")
    optparser.add_option("-n", "--negatives", default=False, action="store_true", help="")
    optparser.add_option("-c", "--corpus", default="SE10T8", help="")
    optparser.add_option("-p", "--preprocess", default=False, action="store_true", help="")
    optparser.add_option("--constParser", default=None)
    optparser.add_option("--depParser", default=None)
    optparser.add_option("-d", "--debug", default=False, action="store_true", help="")
    optparser.add_option("--clear", default=False, action="store_true", help="")
    optparser.add_option("--noLog", default=False, action="store_true", dest="noLog", help="")
    (options, args) = optparser.parse_args()
    
    if not options.noLog:
        Stream.openLog(os.path.join(options.outdir, "log.txt"))
    
    convert(options.input, options.outdir, directed=options.directed, negatives=options.negatives, 
            preprocess=options.preprocess, corpusId=options.corpus,
            constParser=options.constParser, depParser=options.depParser, 
            debug=options.debug, clear=options.clear)