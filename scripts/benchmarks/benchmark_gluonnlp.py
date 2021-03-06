import mxnet as mx
import argparse
import os
import pandas as pd
from benchmark_utils import GluonNLPBackboneBenchmark
import multiprocessing as mp
from multiprocessing import Process
mx.npx.set_np()


MODELS = [
    'google_en_uncased_bert_base',
    'google_en_uncased_bert_large',
    'google_albert_base_v2',
    'google_albert_large_v2',
    'google_albert_xlarge_v2',
    'google_albert_xxlarge_v2',
    'google_electra_small',
    'google_electra_base',
    'google_electra_large',
    'google_uncased_mobilebert',
    'fairseq_bart_base',
    'fairseq_bart_large'
]

# (batch_size, seq_length)
train_workloads =\
    [(4, 128),
     (8, 128),
     (16, 128),
     (32, 128),
     (1, 512),
     (2, 512),
     (4, 512),
     (8, 512)]


inference_workloads = [
    (1, 128),
    (1, 384),
    (1, 512),
    (8, 32),
    (8, 128),
    (8, 512),
    (32, 512),
    (256, 128),
    (400, 100),
]


def get_parser():
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--layout', type=str, default='NT',
                        help='The layout of the computation')
    parser.add_argument('--compute_layout', type=str, default=None,
                        help='The compute layout of the computation')
    parser.add_argument('--use_tvm', action='store_true',
                        help='Whether to use TVM for inference/training')
    parser.add_argument('--instance_type', choices=['c4', 'c5', 'g4', 'p3'], default='g4',
                        help='The instance type that the profiling script will be run on.')
    parser.add_argument('--use_fp16', action='store_true')
    parser.add_argument('--mode', type=str, default='train',
                        choices=['train', 'inference'])
    return parser


def run_benchmark(workload, model_name, out_file_name, is_train,
                  use_tvm, instance_type, use_fp16):
    if is_train:
        benchmark = GluonNLPBackboneBenchmark(
            workloads=workload,
            model_names=model_name,
            profile_inference=False,
            profile_train=True,
            to_csv=True,
            use_fp16=use_fp16,
            train_out_csv_file=out_file_name)
        benchmark.run()
    else:
        benchmark = GluonNLPBackboneBenchmark(
            workloads=workload,
            model_names=model_name,
            profile_inference=True,
            profile_train=False,
            use_tvm=use_tvm,
            instance_type=instance_type,
            to_csv=True,
            use_fp16=use_fp16,
            inference_out_csv_file=out_file_name)
        benchmark.run()
    return


if __name__ == '__main__':
    mp.set_start_method('spawn')
    parser = get_parser()
    args = parser.parse_args()
    if args.compute_layout is None:
        args.compute_layout = args.layout
    dtype = 'float32' if not args.use_fp16 else 'float16'
    for layout, compute_layout in [(args.layout, args.compute_layout)]:
        if compute_layout != layout:
            profile_models = [ele for ele in MODELS if 'bart' not in ele]
        else:
            profile_models = [ele for ele in MODELS]
        if args.mode == 'inference':
            out_dir = 'infer_{}_{}_{}_tvm{}'.format(dtype, layout, compute_layout,
                                                    int(args.use_tvm))
            df = pd.DataFrame(columns=['model', 'batch_size', 'sequence_length',
                                       'latency', 'memory'])
            os.makedirs(out_dir, exist_ok=True)
            for model_name in profile_models:
                for workload in inference_workloads:
                    out_path = os.path.join(out_dir, '{}_{}_{}.csv'.format(model_name, workload[0],
                                                                           workload[1]))
                    process = Process(
                        target=run_benchmark,
                        args=(workload, model_name, out_path, False,
                              args.use_tvm, args.instance_type, args.use_fp16))
                    process.start()
                    process.join()
                    new_df = pd.read_csv(out_path)
                    df = df.append(new_df, ignore_index=True)
                    df.to_csv('gluonnlp_infer_{}_{}_{}_tvm{}.csv'.format(dtype,
                                                                         layout,
                                                                           compute_layout,
                                                                           int(args.use_tvm)))
        elif args.mode == 'train':
            out_dir = 'train_{}_{}_{}'.format(dtype, layout, compute_layout)
            df = pd.DataFrame(columns=['model', 'batch_size', 'sequence_length',
                                       'latency', 'memory'])
            os.makedirs(out_dir, exist_ok=True)
            for model_name in profile_models:
                for workload in train_workloads:
                    out_path = os.path.join(out_dir, '{}_{}_{}.csv'.format(model_name, workload[0],
                                                                           workload[1]))
                    process = Process(
                        target=run_benchmark,
                        args=(workload, model_name, out_path, True, False,
                              args.instance_type, args.use_fp16))
                    process.start()
                    process.join()
                    new_df = pd.read_csv(out_path)
                    df = df.append(new_df, ignore_index=True)
                    df.to_csv('gluonnlp_train_{}_{}_{}.csv'.format(dtype, layout, compute_layout))
        else:
            raise NotImplementedError
