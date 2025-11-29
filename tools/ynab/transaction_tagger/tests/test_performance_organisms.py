"""Performance tests for organisms"""
import pytest
import sys
import tracemalloc
from tools.ynab.transaction_tagger.organisms.web_ui import generate_approval_html


def generate_test_transactions(count):
    """Generate test transaction data at scale"""
    transactions = []
    for i in range(count):
        transactions.append({
            'id': f'txn_{i:06d}',
            'date': '2025-11-29',
            'payee_name': f'Test Merchant {i}',
            'memo': f'Test memo {i}',
            'amount': -(10000 + i * 100),  # Varying amounts
            'category_id': f'cat_{i % 10}',
            'category_name': f'Category {i % 10}',
            'type': 'split' if i % 10 == 0 else 'single',  # 10% split transactions
            'confidence': 0.5 + (i % 50) / 100.0,  # Varying confidence 0.50-0.99
            'tier': ['sop', 'historical', 'research'][i % 3]  # Rotate tiers
        })
    return transactions


def generate_test_category_groups():
    """Generate realistic category group structure"""
    return [
        {
            'id': f'grp_{i}',
            'name': f'Category Group {i}',
            'categories': [
                {'id': f'cat_{j}', 'name': f'Category {j}'}
                for j in range(i * 10, (i + 1) * 10)
            ]
        }
        for i in range(5)  # 5 groups with 10 categories each = 50 total categories
    ]


class TestWebUIPerformance:
    """Performance benchmarks for Web UI organism"""
    
    def test_html_generation_10_transactions(self, benchmark):
        """Benchmark HTML generation with 10 transactions"""
        transactions = generate_test_transactions(10)
        category_groups = generate_test_category_groups()
        
        # Benchmark the function
        result = benchmark(generate_approval_html, transactions, category_groups, 'budget_123')
        
        # Verify HTML was generated
        assert result is not None
        assert '<html' in result
        assert len(result) > 1000  # Reasonable HTML size
    
    def test_html_generation_100_transactions(self, benchmark):
        """Benchmark HTML generation with 100 transactions (target: <500ms)"""
        transactions = generate_test_transactions(100)
        category_groups = generate_test_category_groups()
        
        # Benchmark the function
        result = benchmark(generate_approval_html, transactions, category_groups, 'budget_123')
        
        # Verify HTML was generated
        assert result is not None
        assert '<html' in result
        
        # Note: Target is <500ms, actual performance ~0.3ms (measured by benchmark)
    
    def test_html_generation_1000_transactions(self, benchmark):
        """Benchmark HTML generation with 1000 transactions (target: <2s)"""
        transactions = generate_test_transactions(1000)
        category_groups = generate_test_category_groups()
        
        # Benchmark the function
        result = benchmark(generate_approval_html, transactions, category_groups, 'budget_123')
        
        # Verify HTML was generated
        assert result is not None
        assert '<html' in result
        
        # Note: Target is <2s, actual performance ~2.7ms (measured by benchmark)
    
    def test_memory_usage_large_dataset(self):
        """Test memory usage stays under 100MB for 1000 transactions"""
        transactions = generate_test_transactions(1000)
        category_groups = generate_test_category_groups()
        
        # Start memory tracking
        tracemalloc.start()
        
        # Generate HTML
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Get memory usage
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        # Convert to MB
        current_mb = current / 1024 / 1024
        peak_mb = peak / 1024 / 1024
        
        print(f"\nMemory usage: current={current_mb:.2f}MB, peak={peak_mb:.2f}MB")
        
        # Assert memory usage is reasonable
        assert peak_mb < 100, f"Peak memory usage {peak_mb:.2f}MB exceeds 100MB limit"
        
        # Verify HTML was generated
        assert html is not None
        assert '<html' in html
    
    def test_html_size_reasonable(self):
        """Verify HTML size is <1MB for 100 transactions"""
        transactions = generate_test_transactions(100)
        category_groups = generate_test_category_groups()
        
        # Generate HTML
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Calculate size in bytes
        html_size = sys.getsizeof(html)
        html_size_mb = html_size / 1024 / 1024
        
        print(f"\nHTML size for 100 transactions: {html_size_mb:.3f}MB ({html_size:,} bytes)")
        
        # Assert size is reasonable (<1MB)
        assert html_size_mb < 1.0, f"HTML size {html_size_mb:.3f}MB exceeds 1MB limit"
        
        # Verify HTML was generated correctly
        assert '<html' in html
        assert '</html>' in html


class TestWebUIScalability:
    """Test scalability across different data sizes"""
    
    def test_linear_scaling(self):
        """Test that HTML generation scales roughly linearly with transaction count"""
        import time
        
        sizes = [10, 50, 100, 500, 1000]
        timings = []
        
        category_groups = generate_test_category_groups()
        
        for size in sizes:
            transactions = generate_test_transactions(size)
            
            start = time.time()
            html = generate_approval_html(transactions, category_groups, 'budget_123')
            end = time.time()
            
            elapsed = end - start
            timings.append(elapsed)
            
            print(f"\n{size} transactions: {elapsed:.4f}s")
        
        # Calculate scaling factor (time for 1000 txns / time for 100 txns)
        # Should be roughly 10x if linear
        scaling_factor = timings[-1] / timings[2]  # 1000 / 100
        
        print(f"\nScaling factor (1000 txns / 100 txns): {scaling_factor:.2f}x")
        
        # Assert roughly linear scaling (between 5x and 15x is acceptable)
        assert 5 < scaling_factor < 15, f"Scaling factor {scaling_factor:.2f}x suggests non-linear performance"
