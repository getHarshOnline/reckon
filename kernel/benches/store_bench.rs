//! Native store timings with fixture construction outside the measured operations.

use criterion::{criterion_group, criterion_main, BatchSize, Criterion, Throughput};
use reckon_kernel::{Record, RecordStore};
use std::{hint::black_box, time::Duration};

fn records(count: usize) -> Vec<Record> {
    (0..count)
        .map(|index| {
            let mut record = Record::new(
                format!("r{index}"),
                index as i64,
                "trial".into(),
                "observation".into(),
                vec![0; 100],
                100,
            );
            record.utility = (index % 100) as f64 / 100.0;
            record
        })
        .collect()
}

fn filled_store(count: usize) -> RecordStore {
    let store = RecordStore::new(count);
    for record in records(count) {
        store.insert(record).unwrap();
    }
    store
}

fn benchmark_insert(c: &mut Criterion) {
    let mut group = c.benchmark_group("store_insert");
    group.throughput(Throughput::Elements(1000));
    group.bench_function("1000_records_100_bytes", |b| {
        b.iter_batched_ref(
            || (RecordStore::new(1000), records(1000)),
            |(store, input)| {
                for record in input.drain(..) {
                    black_box(store.insert(black_box(record)).unwrap());
                }
            },
            BatchSize::PerIteration,
        );
    });
    group.finish();
}

fn benchmark_get(c: &mut Criterion) {
    let store = filled_store(1000);
    let keys = (0..100).map(|i| format!("r{}", i * 10)).collect::<Vec<_>>();
    let mut group = c.benchmark_group("store_get");
    group.throughput(Throughput::Elements(100));
    group.bench_function("100_spaced_keys_in_1000", |b| {
        b.iter(|| {
            for key in &keys {
                black_box(store.get(black_box(key)));
            }
        })
    });
    group.finish();
}

fn benchmark_select_for_pruning(c: &mut Criterion) {
    let store = filled_store(10000);
    assert_eq!(store.select_for_pruning(10000).len(), 100);
    c.bench_function("store_select_100_of_10000", |b| {
        b.iter(|| black_box(store.select_for_pruning(black_box(10000))))
    });
}

criterion_group! {
    name = benches;
    config = Criterion::default().sample_size(30)
        .warm_up_time(Duration::from_secs(1)).measurement_time(Duration::from_secs(3));
    targets = benchmark_insert, benchmark_get, benchmark_select_for_pruning
}
criterion_main!(benches);
