import requests
from SPARQLWrapper import SPARQLWrapper, JSON


class EntryLinker(object):
    def __init__(self, graph, base_uri):
        self.base_uri = base_uri
        self.graph = graph

    def reconcile(self):
        pass

    def display_possibilities(self, entry, possibilities):
        print("Possibilities for %s" % entry)
        for i in range(len(possibilities)):
            item_dict = possibilities[i]
            dict_rep = [("%s: %s" % (key, value)) for key, value in item_dict.items()]
            rep = "[%s] %s" % (i, ", ".join(dict_rep))
            print(rep)

    def get_user_choice(self, choices):
        no_answer_given = True
        while no_answer_given:
            index = input("Give me an index \"X\" for abort: ")
            if index == "X":
                return None
            else:  # TODO: don't missuse exception for programm logic
                try:
                    i = int(index)
                except ValueError:
                    continue
                if len(choices) > i:
                    return choices[i]

    def make_uri(self, name, type):
        sane_name = name.lower().replace('/', '--').strip().replace(' ', '_')
        return self.base_uri + type + "/" + sane_name


class OrganizationLinker(EntryLinker):
    def __init__(self, graph, base_uri):
        super().__init__(graph, base_uri)

    def reconcile(self):
        get_publisher_names_query = """
        PREFIX dct: <http://purl.org/dc/terms/>
        PREFIX foaf: <http://xmlns.com/foaf/0.1/>
        SELECT DISTINCT ?p ?name WHERE { 
         [] dct:publisher ?p . ?p foaf:name ?name
        }"""
        res = self.graph.query(get_publisher_names_query)
        publisher_names = set(row[1] for row in res)
        for name in publisher_names:
            self.reconcile_single(name)

    def reconcile_single(self, name):
        pub_uri = self.make_uri(name, "organization")

        make_separate_entry_for_publisher_query = f"""
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
DELETE {{ ?x dct:publisher ?pub . ?pub foaf:name "{name}" ; ?p ?y }}
INSERT {{ ?x dct:publisher <{pub_uri}> . <{pub_uri}> foaf:name "{name}" ; ?p ?y }}
WHERE {{ 
    ?x dct:publisher ?pub . ?pub foaf:name "{name}" ; ?p ?y
}}"""
        self.graph.update(make_separate_entry_for_publisher_query)

    def fetch_description_from_wikidata(self, wiki_data_urls):
        """
        Receives a list of wiki data urls and fetches human
        readable data for them to ease the annotators job of disambiguating
        :param wiki_data_urls:
        :return:
        """
        descs = []
        for link in wiki_data_urls:
            wikidata_query = f"""
    PREFIX wd: <http://www.wikidata.org/prop/direct/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX schema: <http://schema.org/>
    SELECT DISTINCT ?entity_label ?instance_label ?desc 
    WHERE {{
      <{link}> wd:P31 ?instance.
      OPTIONAL {{
        <{link}> schema:description ?desc.
        FILTER (lang(?desc) = "en" || lang(?desc) = "")
        }}.
      ?instance rdfs:label ?instance_label.
      <{link}> rdfs:label ?entity_label.
      FILTER (lang(?entity_label) = "en" || lang(?entity_label) = "")
      FILTER (lang(?instance_label) = "en" || lang(?instance_label) = "")
    }}
    """
            sparql = SPARQLWrapper('https://query.wikidata.org/sparql')
            sparql.setQuery(wikidata_query)
            sparql.setReturnFormat(JSON)
            result = sparql.query().convert()["results"]["bindings"][0]
            desc_dict = {key: result[key]["value"] for key in ["instance_label", "entity_label", "desc"] if
                         key in result.keys()}
            desc_dict["url"] = link
            descs.append(desc_dict)
        return descs

    def backup_babelfy(self, name):
        payload = {'key': 'KEY', 'text': name}
        req = "http://babelfy.io/v1/disambiguate"
        resp = requests.get(req, params=payload)
        try:
            dburl = resp.json()[0]["DBpediaURL"]
        except KeyError:
            return None
        dbpedia = SPARQLWrapper('https://dbpedia.org/sparql')
        dbquery = f"""
        PREFIX owl: <http://www.w3.org/2002/07/owl#> 
        SELECT DISTINCT ?same WHERE{{
            <{str(dburl)}> a <http://dbpedia.org/ontology/Organisation>; owl:sameAs ?same 
            FILTER (STRSTARTS(str(?same), "http://www.wikidata.org/entity/"))
        }}
        """
        dbpedia.setQuery(dbquery)
        dbpedia.setReturnFormat(JSON)
        results = dbpedia.query().convert()
        res = results['results']['bindings']
        if len(res) > 0:
            print(res[0]['same']['value'])
            return res[0]['same']['value']

    def figure_out_correct_link(self, name):
        wikidata_lookup = f"""
    PREFIX wd: <http://www.wikidata.org/prop/direct/>
    SELECT DISTINCT ?x
    WHERE {{ 
        VALUES(?label) {{
           ( "{name}" )
           ( "{name}"@en )
           ( "{name}"@de )
          }}
        ?x ?p ?label
         ; wd:P31/wd:P279* <http://www.wikidata.org/entity/Q43229>
    }}
    """
        sparql = SPARQLWrapper('https://query.wikidata.org/sparql')
        sparql.setQuery(wikidata_lookup)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()["results"]["bindings"]
        if len(results) > 1:
            descs = self.fetch_description_from_wikidata([result["x"]["value"] for result in results])
            self.display_possibilities(name, descs)
            result = self.get_user_choice(descs)
            if result is None:
                return self.backup_babelfy(name)
            return result["url"]
        if len(results) == 0:
            return self.backup_babelfy(name)
        if len(results) == 1:
            print("Adding %s." % results[0]["x"]["value"])