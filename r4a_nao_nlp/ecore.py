"""Contains functions that handle ecore metamodels."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Iterable, List, Optional

import pyecore
from pyecore.ecore import EClass, EEnum, EObject
from pyecore.resources import URI, ResourceSet

from r4a_nao_nlp import utils

if TYPE_CHECKING:
    from r4a_nao_nlp.typing import SnipsResult, Node

logger = utils.create_logger(__name__)
mm_root = None


def init_root(path_to_ecore: str) -> None:
    """Load the root metamodel from the given path."""
    logger.debug("Initializing mm_root from %s", path_to_ecore)

    global mm_root
    mm_root = ResourceSet().get_resource(URI(path_to_ecore)).contents[0]


def save_objects(*objects: EObject, path: str = "./out.highlevelnaoapp") -> None:
    """Save objects to the given path."""
    resource = ResourceSet().create_resource(URI(path))
    for obj in objects:
        resource.append(obj)
    resource.save()


def naoapp_from_nodes(nodes: Iterable[Node], name: Optional[str] = None) -> EObject:
    """Create the top level NaoApp that will contain the given nodes."""
    naoapp = create_nao_app(name)

    for node in nodes:
        if isinstance(node, str):
            continue

        naoapp.hasActivity.insert(-1, node.parsed.to_eobject())

    return naoapp


def create_nao_app(name: str = "r4a_nao_nlp app") -> EObject:
    """Create a top level NaoApp object with a Start and Finish."""
    naoapp = mm_root.getEClassifier("NaoApp")(name=name)
    naoapp.hasActivity.add(mm_root.getEClassifier("Start")())
    naoapp.hasActivity.add(mm_root.getEClassifier("Finish")())
    return naoapp


def snips_result_to_eobject(result: SnipsResult) -> EObject:
    """Convert given `SnipsResult` to an `EObject` of the corresponding `EClass`."""
    assert mm_root is not None
    if not result:
        raise ValueError("SnipsResult argument should evaluate to True")

    eclass = mm_root.getEClassifier(result.name)
    eobject = eclass()
    for slot in result:
        eattribute = _getEAttribute(eclass, slot.name)

        value = eattribute.eType.from_string(str(slot))
        if eattribute.many:
            getattr(eobject, eattribute.name).append(value)
        else:
            setattr(eobject, eattribute.name, value)
    return eobject


def _getEAttribute(eclass: EClass, name: str) -> pyecore.ecore.EAttribute:
    for attr in eclass.eAttributes:
        if attr.name == name:
            return attr
    raise ValueError(f"EClass '{eclass.name}' does not contain EAttribute '{name}'")


def main(argv: List[str]) -> None:
    """Main function that calls the YAML generator."""
    parser = utils.ArgumentParser()
    parser.add_ecore_root_argument("-r", "--root")

    parser.parse_args(argv[1:])
    generate_yaml()


def generate_yaml() -> None:
    """Generate YAML intent and entity file skeletons from root metamodel.

    Intents are saved in ./intent_{name}.yaml files if the utterance file exists for the
    given name.
    Entities are saved in ./entity_{name}.yaml files.
    """
    import yaml
    import networkx as nx

    def dump(d):
        logger.debug("Dumping %s %s", d["type"], d["name"])
        return "---\n" + yaml.dump(d, default_flow_style=False, indent=4)

    g = nx.Graph()
    for eclassifier in mm_root.eClassifiers:
        logger.debug("Processing eclassifier %s", eclassifier.name)

        if isinstance(eclassifier, EClass):
            if not _utterances_filename(eclassifier.name):
                logger.warn(
                    "Eclassifier %s does not contain any utterances, skipping",
                    eclassifier.name,
                )
                continue

            d = {"type": "intent", "name": eclassifier.name, "slots": []}
            for eattribute in eclassifier.eAttributes:
                d_a = _eattribute_to_dict(eattribute)
                type_name = d_a["name"]
                d["slots"].append({"name": eattribute.name, "entity": type_name})
                if isinstance(eattribute.eType, EEnum):
                    # EEnums should be handled later in the loop
                    g.add_edge(eclassifier, eattribute.eType)
                    continue
                if "type" in d_a:
                    g.add_node(type_name, intent=False, d=d_a)
                    g.add_edge(eclassifier, type_name)
            g.add_node(eclassifier, intent=True, d=d)
        elif isinstance(eclassifier, EEnum):
            g.add_node(eclassifier, intent=False, d=_enum_to_dict(eclassifier))
        else:
            logger.error(
                "eclassifier %s is of unkown type %s", eclassifier, type(eclassifier)
            )

    for node, data in g.nodes(data=True):
        if not data:
            logger.debug("eclassifier %s didn't get any data", node.name)
            continue
        if data["intent"]:
            others = "\n".join(
                dump(g.nodes[eattribute]["d"])
                for eattribute in g.adj[node]
                if len(g.adj[eattribute]) == 1
            )
            d = data["d"]
            with open("intent_" + d["name"] + ".yaml", "w") as f:
                if others:
                    print(others, file=f)
                print(dump(d).strip(), file=f)
        else:
            if len(g.adj[node]) == 1:
                continue
            d = data["d"]
            with open("entity_" + d["name"] + ".yaml", "w") as f:
                print(dump(d).strip(), file=f)


def _eattribute_to_dict(eattribute):
    if isinstance(eattribute.eType, EEnum):
        return _enum_to_dict(eattribute.eType)

    result = {"type": "entity"}
    result["name"] = eattribute.name[0].upper() + eattribute.name[1:]
    if eattribute.eType.eType == bool:
        if eattribute.name[0] == "b" and eattribute.name[1].isupper():
            # bDetectForever -> DetectForever
            result["name"] = eattribute.name[1:]
        result["automatically_extensible"] = False
        result["values"] = ["TRUE", "FALSE"]
        return result

    if eattribute.eType.eType in (int, float):
        # TODO: don't add edge
        return {"name": "snips/number"}
    if eattribute.eType.eType == str:
        result["automatically_extensible"] = True
    return result


def _enum_to_dict(enum):
    return {
        "type": "entity",
        "name": enum.name,
        "automatically_extensible": False,
        "values": [literal.name for literal in enum.eLiterals],
    }


def _utterances_filename(eclass_name: str) -> Optional[str]:
    data_file = os.path.join("data", "utterances_" + eclass_name)
    return data_file if os.path.exists(data_file) else None


if __name__ == "__main__":
    from r4a_nao_nlp import __main__

    __main__.entry_point(__spec__.name)

# vim:ts=4:sw=4:expandtab:fo-=t:tw=88
