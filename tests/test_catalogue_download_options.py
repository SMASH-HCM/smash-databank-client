import copy

import pytest

from smash_hcm_databank_client.download_flow import download
from smash_hcm_databank_client.listing import file_labels, table_labels
from smash_hcm_databank_client.manifest import artifact_type, validate_manifest, ManifestError
from smash_hcm_databank_client.manifest_browser import ManifestTree, browse
from smash_hcm_databank_client.menu_ui import actions
from smash_hcm_databank_client.nextcloud import NextcloudError
from smash_hcm_databank_client.presentation import status_panel
from test_download_flow import answers, item, workspace


@pytest.mark.parametrize('kind,category', [
    ('clinical-data','tables'), ('clinical-landmarks','tables'), ('curated-bundle','curated'),
    ('event-stream','events'), ('cohort-summary','reports'), ('omop-database','database'), ('etl-output','etl'),
])
def test_explicit_category_overrides_csv_extension(kind, category):
    entry = item('somewhere/file.csv', ['FLORENCE-TRAIN'], kind=kind)
    assert artifact_type(validate_manifest({'schema_version':'1.0','release':'fixture','files':[entry]})['files'][0]) == category


def test_existing_cohort_and_etl_directories_classify_without_membership_inference():
    for path, category in [('cohorts/v1.4/cohort_landmarks.csv','reports'),('smash-etl/output/measurements.csv','etl')]:
        data = validate_manifest({'schema_version':'1.0','release':'fixture','files':[item(path)]})
        assert artifact_type(data['files'][0]) == category
        assert data['files'][0]['cohorts'] == []
    assert artifact_type(item('cohorts/explicit.csv',kind='clinical-data')) == 'tables'


@pytest.mark.parametrize('layout',['files','entries'])
def test_optional_folder_comments_and_kind_inheritance_round_trip(layout):
    folder = {'path':'cohorts','type':'directory','comment':'Cohort definitions and summaries','kind':'cohort-summary'}
    files = [item('cohorts/landmarks.csv', comment='One row per landmark')]
    raw = {'schema_version':'1.0','release':'fixture',layout:files}
    if layout == 'entries': raw[layout].append(folder)
    else: raw['directories']=[folder]
    original = copy.deepcopy(raw)
    result = validate_manifest(raw)
    assert raw == original
    assert validate_manifest(result) == result
    assert artifact_type(result['files'][0]) == 'reports'
    tree = ManifestTree(result)
    assert tree.directories['cohorts']['comment'] == folder['comment']
    assert tree.files['cohorts/landmarks.csv']['comment'] == 'One row per landmark'


@pytest.mark.parametrize('folder',[False,True])
def test_comments_must_be_strings(folder):
    entry = {'path':'folder','type':'directory','comment':[]} if folder else item('test.zip',comment=12)
    with pytest.raises(ManifestError,match='comment'):
        validate_manifest({'schema_version':'1.0','release':'fixture','entries':[entry]})


def test_status_table_never_interrogates_a_local_database(tmp_path, monkeypatch):
    state,_ = workspace(tmp_path, [])
    def unexpected():
        raise AssertionError('status panel must not inspect a database')
    monkeypatch.setattr(state,'database_available',unexpected)
    panel = status_panel(state,100)
    assert 'OMOP' not in panel and 'database:' not in panel


def test_download_menu_has_requested_order_and_legacy_folder_availability(tmp_path):
    state,_ = workspace(tmp_path, [item('cohorts/summary.csv'),item('smash-etl/results.csv')])
    options = [action for action in actions(state) if action.group=='Download']
    assert [action.label for action in options] == [
        'Cohort clinical data','Cohort data bundles (MRI / Echo / ECG)','Cohort event stream datasets',
        'Cohort summaries','Harmonized OMOP PostgreSQL dump (advanced)',
        'SMASH-HCM ETL output (advanced)','Download specific file(s) / folder']
    assert options[3].enabled and options[5].enabled and not options[0].enabled


@pytest.mark.parametrize('folder',['','zips','curated'])
def test_protected_roots_have_no_bulk_actions_and_cannot_multiselect_entire_tree(tmp_path, folder):
    prefix=folder+'/' if folder else ''
    state,server = workspace(tmp_path,[item(prefix+'a.zip'),item(prefix+'b.zip')])
    tree=ManifestTree(state.manifest())
    assert not tree.bulk_allowed(folder)
    with pytest.raises(NextcloudError,match='Downloading all files'):
        tree.check_selection(folder,list(tree.files.values()))
    tree.check_selection(folder,[tree.files[prefix+'a.zip']])
    output=[]
    # Root: select-files, folder; protected folder: parent, select-files, a, b.
    browse(state,read=answers(*(['2','0'] if folder else ['0'])),write=output.append,plain=True)
    assert not any('Download files in this folder' in line or 'Download this folder and all subfolders' in line for line in output)
    assert not server.calls


def test_all_zip_selection_is_rejected_before_location_or_transfer(tmp_path):
    state,server=workspace(tmp_path,[item('zips/a.zip'),item('zips/b.zip')])
    output=[]
    assert browse(state,read=answers('2','2','all','0'),write=output.append,plain=True)==[]
    assert any('Downloading all files at this level is disabled' in line for line in output)
    assert not state.state['download_root'] and not server.calls


def test_narrow_clinical_directory_remains_recursive(tmp_path):
    state,server=workspace(tmp_path,[item('curated/FLORENCE/Clinical/train.csv'),item('curated/FLORENCE/Clinical/history/test.csv'),item('curated/RENNES/Clinical/test.csv')])
    tree=ManifestTree(state.manifest())
    assert tree.bulk_allowed('curated/FLORENCE/Clinical')
    assert len(tree.select_folder('curated/FLORENCE/Clinical',recursive=True))==2


def test_file_size_and_comment_columns_align_and_controls_are_not_executed():
    rows=table_labels([('[File] short.zip','1.0 MiB','reference only'),('[File] much-longer.zip','384.6 MiB','\nno newline\t')])
    assert [i for i,c in enumerate(rows[0]) if c=='|']==[i for i,c in enumerate(rows[1]) if c=='|']
    assert rows[1].endswith('no newline')
    labels=file_labels([item('a.zip',comment='MAT reference'),item('long-name.zip',comment='')])
    assert labels['a.zip'].endswith('MAT reference')


def test_clinical_selection_includes_matching_landmarks_but_not_other_preprocessing(tmp_path):
    entries=[item('clinical/train.csv',['FLORENCE-TRAIN'],kind='clinical-data',preprocessing='baseline',split='train'),
             item('clinical/train-landmarks.csv',['FLORENCE-TRAIN'],kind='clinical-landmarks',preprocessing='baseline',role='landmarks'),
             item('clinical/train-history.csv',['FLORENCE-TRAIN'],kind='clinical-data',preprocessing='history-730d')]
    state,server=workspace(tmp_path,entries)
    result=download(state,'tables',read=answers('all','1','c',str(tmp_path/'data'),'y'),write=lambda _:None,plain=True)
    assert len(result)==2 and set(server.calls)=={'clinical/train.csv','clinical/train-landmarks.csv'}


def test_etl_advanced_downloads_selected_files_without_cohort_tags(tmp_path):
    state,server=workspace(tmp_path,[item('smash-etl/a.csv'),item('smash-etl/b.csv')])
    result=download(state,'etl',read=answers('1','c',str(tmp_path/'data'),'y'),write=lambda _:None,plain=True)
    assert len(result)==1 and server.calls==['smash-etl/a.csv']
