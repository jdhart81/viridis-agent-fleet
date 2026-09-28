import copy
import pytest
from fleet_utils.orc_witness import ZERO, sha, merkle, inclusion, root_hash, verify_proof, save_witness

@pytest.mark.parametrize('count',[0,1,2,3,1000])
def test_LG3_merkle_fixtures(count):
    leaves=[sha(str(i)) for i in range(count)]; hour='2026-09-28T01'; tree=merkle(leaves)
    root={'hour':hour,'count':count,'prev_root':ZERO,'merkle_root':tree,'root':root_hash(ZERO,tree,hour,count)}
    if not count: assert tree==sha(''); return
    for index in {0,count//2,count-1}:
        proof={'hour':hour,'commitment':leaves[index],'index':index,'path':inclusion(leaves,index)}
        assert verify_proof(proof,root)
        bad=copy.deepcopy(proof);bad['commitment']=sha('tamper')
        assert not verify_proof(bad,root)
        bad=copy.deepcopy(proof);bad['index']=count
        assert not verify_proof(bad,root)

def test_LG4_witness_new_idempotent_conflict(tmp_path):
    root={'hour':'2026-09-28T01','count':0,'prev_root':ZERO,'merkle_root':merkle([])}
    root['root']=root_hash(ZERO,root['merkle_root'],root['hour'],0)
    assert save_witness(root,tmp_path)
    assert not save_witness(root,tmp_path)
    other=dict(root,prev_root=sha('other'));other['root']=root_hash(other['prev_root'],other['merkle_root'],other['hour'],0)
    with pytest.raises(ValueError,match='conflict'): save_witness(other,tmp_path)
    with pytest.raises(ValueError,match='invalid'): save_witness(dict(root,hour='../bad'),tmp_path)
