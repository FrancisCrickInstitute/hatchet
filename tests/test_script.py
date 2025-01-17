import pytest
import sys
import os
import glob
from io import StringIO
from mock import patch
import shutil
import pandas as pd
from pandas.testing import assert_frame_equal

import hatchet
from hatchet import config
from hatchet.utils.binBAM import main as binBAM
from hatchet.utils.SNPCaller import main as SNPCaller
from hatchet.utils.deBAF import main as deBAF
from hatchet.utils.comBBo import main as comBBo
from hatchet.utils.cluBB import main as cluBB
from hatchet.utils.BBot import main as BBot
from hatchet.bin.HATCHet import main as main
from hatchet.utils.BBeval import main as BBeval

this_dir = os.path.dirname(__file__)
SOLVE = os.path.join(os.path.dirname(hatchet.__file__), 'solve')


@pytest.fixture(scope='module')
def bams():
    bam_directory = config.tests.bam_directory
    normal_bam = os.path.join(bam_directory, 'normal.bam')
    if not os.path.exists(normal_bam):
        pytest.skip('File not found: {}/{}'.format(bam_directory, normal_bam))
    tumor_bams = sorted([f for f in glob.glob(bam_directory + '/*.bam') if os.path.basename(f) != 'normal.bam'])
    if not tumor_bams:
        pytest.skip('No tumor bams found in {}'.format(bam_directory))

    return normal_bam, tumor_bams


@pytest.fixture(scope='module')
def output_folder():
    out = os.path.join(this_dir, 'out')
    shutil.rmtree(out, ignore_errors=True)
    for sub_folder in ('bin', 'snps', 'baf', 'bb', 'bbc', 'plots', 'results', 'evaluation', 'analysis'):
       os.makedirs(os.path.join(out, sub_folder))
    return out


@pytest.mark.skipif(not config.paths.reference, reason='paths.reference not set')
@pytest.mark.skipif(not config.paths.samtools, reason='paths.samtools not set')
@pytest.mark.skipif(not config.paths.bcftools, reason='paths.bcftools not set')
@patch('hatchet.utils.ArgParsing.extractChromosomes', return_value=['chr22'])
def test_script(_, bams, output_folder):
    normal_bam, tumor_bams = bams

    binBAM(
        args=[
            '-N', normal_bam,
            '-T'
        ] + tumor_bams + [
            '-b', '50kb',
            '-st', config.paths.samtools,
            '-S', 'Normal', 'Tumor1', 'Tumor2', 'Tumor3',
            '-g', config.paths.reference,
            '-j', '12',
            '-q', '11',
            '-O', os.path.join(output_folder, 'bin/normal.1bed'),
            '-o', os.path.join(output_folder, 'bin/bulk.1bed'),
            '-v'
        ]
    )

    SNPCaller(
        args=[
            '-N', normal_bam,
            '-r', config.paths.reference,
            '-c', '290',    # min reads
            '-C', '300',  # max reads
            '-R', '',
            '-o', os.path.join(output_folder, 'snps'),
            '-st', config.paths.samtools,
            '-bt', config.paths.bcftools,
            '-j', '1'
        ]
    )

    deBAF(
        args=[
            '-bt', config.paths.bcftools,
            '-st', config.paths.samtools,
            '-N', normal_bam,
            '-T'
        ] + tumor_bams + [
            '-S', 'Normal', 'Tumor1', 'Tumor2', 'Tumor3',
            '-r', config.paths.reference,
            '-j', '12',
            '-q', '11',
            '-Q', '11',
            '-U', '11',
            '-c', '8',
            '-C', '300',
            '-O', os.path.join(output_folder, 'baf/normal.1bed'),
            '-o', os.path.join(output_folder, 'baf/bulk.1bed'),
            '-L', os.path.join(output_folder, 'snps', 'chr22.vcf.gz'),
            '-v'
        ]
    )

    _stdout = sys.stdout
    sys.stdout = StringIO()

    comBBo(args=[
        '-c', os.path.join(output_folder, 'bin/normal.1bed'),
        '-C', os.path.join(output_folder, 'bin/bulk.1bed'),
        '-B', os.path.join(output_folder, 'baf/bulk.1bed'),
        '-e', '12'
    ])

    out = sys.stdout.getvalue()
    sys.stdout.close()
    sys.stdout = _stdout

    with open(os.path.join(output_folder, 'bb/bulk.bb'), 'w') as f:
        f.write(out)

    cluBB(args=[
        os.path.join(output_folder, 'bb/bulk.bb'),
        '-o', os.path.join(output_folder, 'bbc/bulk.seg'),
        '-O', os.path.join(output_folder, 'bbc/bulk.bbc'),
        '-e', '22171',  # random seed
        '-tB', '0.04',
        '-tR', '0.15',
        '-d', '0.4'
    ])

    df1 = pd.read_csv(os.path.join(output_folder, 'bbc/bulk.seg'), sep='\t')
    df2 = pd.read_csv(os.path.join(this_dir, 'data', 'bulk.seg'), sep='\t')
    assert_frame_equal(df1, df2)

    BBot(args=[
        os.path.join(output_folder, 'bbc/bulk.bbc'),
        '--rundir', os.path.join(output_folder, 'plots')
    ])

    if os.getenv('GRB_LICENSE_FILE') is not None:
        main(args=[
            SOLVE,
            '-x', os.path.join(output_folder, 'results'),
            '-i', os.path.join(output_folder, 'bbc/bulk'),
            '-n2',
            '-p', '400',
            '-v', '3',
            '-u', '0.03',
            '-r', '6700',  # random seed
            '-j', '8',
            '-eD', '6',
            '-eT', '12',
            '-g', '0.35',
            '-l', '0.6'
        ])

        df1 = pd.read_csv(os.path.join(output_folder, 'results/best.bbc.ucn'), sep='\t')
        df2 = pd.read_csv(os.path.join(this_dir, 'data', 'best.bbc.ucn'), sep='\t')
        assert_frame_equal(df1, df2)

        BBeval(args=[
            os.path.join(output_folder, 'results/best.bbc.ucn'),
            '--rundir', os.path.join(output_folder, 'evaluation')
        ])
