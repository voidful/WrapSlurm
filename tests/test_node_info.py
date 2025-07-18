import builtins
import wrapslurm.node_info as ni

SAMPLE_NODE = """NodeName=hgpn02 Arch=x86_64 CoresPerSocket=16
   CPUAlloc=32 CPUTot=64 CPULoad=20.00
   RealMemory=191997 AllocMem=1024
   CfgTRES=cpu=64,mem=191997M,billing=64,gres/gpu=8
   AllocTRES=cpu=32,mem=1024M,gres/gpu=4
   State=MIXED
   Partitions=gpux
"""

def test_parse_node_data():
    node = ni.parse_node_data(SAMPLE_NODE)
    assert node["NodeName"] == "hgpn02"
    assert node["CPUAlloc"] == 32
    assert node["CPUTot"] == 64
    assert abs(node["CPULoad"] - 20.0) < 0.01
    assert node["GPUAlloc"] == 4
    assert node["GPUTot"] == 8

def test_display_nodes_graph(capsys):
    node = ni.parse_node_data(SAMPLE_NODE)
    ni.display_nodes([node], graph=True)
    captured = capsys.readouterr().out
    assert "hgpn02" in captured
    assert "CPUld" in captured
    assert "#" in captured
