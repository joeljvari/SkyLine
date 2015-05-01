from requests import get
from json import loads, dumps
from collections import defaultdict as dd

server = "localhost:8182"
script_endpoint = (
    "http://"
    + server
    + "/graphs/tinkergraph/tp/gremlin?" )

path_index = { "v": dd(set), "e": dd(set), "p": dd(lambda: []) }
role_index = { "v": dd(lambda: dd(list)), "e": dd(lambda: dd(list)) }
lost_role_index = {"v": dd(dict), "e": dd(dict) }
triggers = {}

path_id = 0
trigger_id = 0

def add_paths_for_edge(e, role):
    global path_id
    trigger = triggers.get(role[0])
    if not trigger: return    
    script = "g.e(%d)" % e
    for i in xrange(role[1]):
        script += ".outV()" if i%2 == 0 else ".inE()"
        script += ".filter " + trigger[role[1]-i-1]
    script += ".path"
    ok, before = run_script(script)
    if not ok:
        raise Exception
    before = map(
        (lambda x: 
         map(lambda y: y['_id'], x)),
        before["results"])
    script = "g.e(%d)" % e
    for i in xrange(role[1]+1, len(trigger)):
        script += ".inV()" if (i-role[1])%2 == 1 else ".outV()"
        script += ".filter " + trigger[i]
    script += ".path"
    ok, after = run_script(script)
    if not ok:
        raise Exception
    after = map(
        (lambda x:
         map(lambda y: y['_id'], x)),
        after["results"])
    for pre in before:
        pre.reverse()
        for post in after:
            path = map(int, pre + post[1:])
            id = path_id
            path_id += 1
            path_index["p"][id] = (role[0], path)
            types = ["v", "e"]
            for i in xrange(len(path)):
                path_index[types[i%2]][path[i]].add(id)
                role_index[types[i%2]][path[i]][(role[0], i)].append(id)
            notify_add_path(id)

def add_paths_for_vertex(v, role):
    global path_id
    trigger = triggers.get(role[0])
    if not trigger: return    
    script = "g.v(%d)" % v
    for i in xrange(role[1]):
        script += ".inE()" if i%2 == 0 else ".outV()"
        script += ".filter " + trigger[role[1]-i-1]
    script += ".path"
    ok, before = run_script(script)
    if not ok:
        raise Exception
    before = map(
        (lambda x: 
         map(lambda y: y['_id'], x)),
        before["results"])
    script = "g.v(%d)" % v
    for i in xrange(role[1]+1, len(trigger)):
        script += ".outE()" if (i-role[1])%2 == 1 else ".inV()"
        script += ".filter " + trigger[i]
    script += ".path"
    ok, after = run_script(script)
    if not ok:
        raise Exception
    after = map(
        (lambda x:
         map(lambda y: y['_id'], x)),
        after["results"])
    for pre in before:
        pre.reverse()
        for post in after:
            path = map(int, pre + post[1:])
            id = path_id
            path_id += 1
            path_index["p"][id] = (role[0], path)
            types = ["v", "e"]
            for i in xrange(len(path)):
                path_index[types[i%2]][path[i]].add(id)
                role_index[types[i%2]][path[i]][(role[0], i)].append(id)
            notify_add_path(id)


def notify_add_path(path):
    print "Path", path, "now matches trigger",
    print path_index["p"][path][0], "with", " -> ".join(
        [("v" if i%2 == 0 else "e") + 
         str(path_index["p"][path][1][i])
         for i in xrange(len(path_index["p"][path][1]))])

def roles_for_edge(e):
    template = "g.e(%d).filter %s"
    lost, gained = [], []
    for t in triggers:
        for i in xrange(1, len(triggers[t]), 2):
            ok, data = run_script(
                template % (e, triggers[t][i]))
            if len(data["results"]) == 1:
                if (t, i) not in role_index["e"][e]:
                    role_index["e"][e][(t, i)] = []
                    gained.append((t, i))
            else:
                if (t, i) in role_index["e"][e]:
                    lost_role_index["e"][e][(t, i)] = (
                        role_index["e"][e][(t, i)])
                    del role_index["e"][e][(t, i)]
                    lost.append((t, i))
    return lost, gained


def roles_for_vertex(v):
    template = "g.v(%d).filter %s"
    lost, gained = [], []
    for t in triggers:
        for i in xrange(0, len(triggers[t]), 2):
            ok, data = run_script(
                template % (v, triggers[t][i]))
            if len(data["results"]) == 1:
                if (t, i) not in role_index["v"][v]:
                    role_index["v"][v][(t, i)] = []
                    gained.append((t, i))
            else:
                if (t, i) in role_index["v"][v]:
                    lost_role_index["v"][v][(t, i)] = (
                        role_index["v"][v][(t, i)])
                    del role_index["v"][v][(t, i)]
                    lost.append((t, i))
    return lost, gained
            
def notify_kill_path(path):
    print "Path", path,
    print "no longer matches trigger", 
    print path_index["p"][path][0]

def kill_path(path):
    notify_kill_path(path)
    i = 0
    part_type = ["v", "e"]
    for part in path_index["p"][path][1]:
        path_index[part_type[i % 2]][part].remove(path)
        i += 1
    del path_index["p"][path]

def kill_paths_for_edge(e, role=None):
    to_kill = []
    if role:
        for path in path_index["e"][e]:
            path_data = path_index["p"][path]        
            if (path_data[0] == role[0]
                and role[1] < len(path_data[1])
                and path_data[1][role[1]] == e):
                to_kill.append(path)
    else:
        for path in path_index["e"][e]:
            to_kill.append(path)
    for path in to_kill:
        kill_path(path)

def kill_paths_for_vertex(v, role=None):
    to_kill = []
    if role:
        for path in lost_role_index["v"][v][role]:
            path_data = path_index["p"][path]        
            if (path_data[0] == role[0]
                and role[1] < len(path_data[1])
                and path_data[1][role[1]] == v):
                to_kill.append(path)
        del lost_role_index["v"][v][role]
    else:
        del role_index["v"][v]
        for path in path_index["v"][v]:
            to_kill.append(path)
    for path in to_kill:
        kill_path(path)

def encode_string(s):
    return "".join(map(
        lambda x:"\u{0:04x}".format(ord(x)), s))

def run_script(script):
    try:
        response = get(script_endpoint, 
                       params={"script": script})
        return (response.ok, loads(response.content))
    except: return (False, None) 

def add_vertex():
    return run_script("g.addVertex()")

def add_edge(v1, v2, label="isSomehowRelatedTo"):
    template = (
        "g.addEdge(g.v(%d), g.v(%d), '%s')")
    script = template % (v1, v2, encode_string(label))
    result = run_script(script)
    if result[0]:
        id = int(result[1]['results'][0]['_id'])
        _, roles = roles_for_edge(id)
        for role in roles:
            add_paths_for_edge(id, role)
    return result

def del_vertex(v):
    kill_paths_for_vertex(v)
    return run_script("g.v(%d).remove()" % (v))

def del_edge(e):
    kill_paths_for_edge(e)
    return run_script("g.e(%d).remove()" % (e))

def set_vertex_attribute(v, attr, val):
    template = (
        "g.v(%d).setProperty("
        + "'%s', new groovy.json.JsonSlurper()"
        + ".parseText('%s').obj)")
    script = (
        template % (v, 
                    encode_string(attr), 
                    encode_string(dumps({"obj":val}))))
    result = run_script(script)
    lost, gained = roles_for_vertex(v)
    for role in lost:
        kill_paths_for_vertex(v, role=role)
    for role in gained:
        add_paths_for_vertex(v, role)
    return result

def set_edge_attribute(e, attr, val):
    template = (
        "g.e(%d).setProperty("
        + "'%s', new groovy.json.JsonSlurper()"
        + ".parseText('%s').obj)")
    script = (
        template % (e, 
                    encode_string(attr), 
                    encode_string(dumps({"obj":val}))))
    result = run_script(script)
    lost, gained = roles_for_edge(e)
    for role in lost:
        kill_paths_for_edge(e, role=role)
    for role in gained:
        add_paths_for_vertex(e, role)
    return result

def run_query(query, start=None, backwards=False, path=False):
    if query == []: return False, None
    join = [".outE()", ".inV()"]
    if backwards:
        join = [".inE()", ".outV()"]
        query.reverse()
    query_script = ["g.V()"]
    if start: query_script[0] = "g.v(%d)" % start
    else: query_script += [".filter", query.pop(0)]
    for i in xrange(len(query)):
        query_script += [join[i%2], ".filter", query[i]]
    if path: query_script += [".path"]
    query_script = "".join(query_script)
    return run_script(query_script)

def add_trigger(query):
    global trigger_id
    triggers[trigger_id] = query
    trigger_id += 1
