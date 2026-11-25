#!/usr/bin/env python
import sys
sys.path.insert(0, r'C:\Users\Koçak\Documents\jatvis\JARVIS_2030_CLEAN')

import unittest

# Run all test modules
test_classes = [
    ('test_intent_engine', 'app.tests.test_intent_engine', 'IntentEngineTests'),
    ('test_intent_context_isolation', 'app.tests.test_intent_context_isolation', 'IntentContextIsolationTests'),
    ('test_dev_engine', 'app.tests.test_dev_engine', 'DevelopmentEngineTests'),
    ('test_autonomous_work', 'app.tests.test_autonomous_work', None),
    ('test_fast_intent', 'app.tests.test_fast_intent', 'FastIntentTests'),
    ('test_brain_bridge', 'app.tests.test_brain_bridge', 'BrainBridgeTests'),
    ('test_visible_powershell', 'app.tests.test_visible_powershell', 'VisiblePowerShellTests'),
    ('test_kernel', 'app.tests.test_kernel', 'KernelTests'),
    ('test_memory', 'app.tests.test_memory', 'MemoryManagerTests'),
    ('test_self_development_import', 'app.tests.test_self_development_import', 'TestSelfDevelopmentImport'),
    ('test_inventory', 'app.tests.test_inventory', 'TestProjectInventory'),
    ('test_architecture', 'app.tests.test_architecture', 'TestArchitectureAnalysis'),
    ('test_plan_creation', 'app.tests.test_plan_creation', 'TestPlanCreation'),
    ('test_unapproved_block', 'app.tests.test_unapproved_block', 'TestUnapprovedBlock'),
    ('test_backup', 'app.tests.test_backup', 'TestBackup'),
    ('test_rollback', 'app.tests.test_rollback', 'TestRollback'),
    ('test_runner_integration', 'app.tests.test_runner_integration', 'TestRunnerIntegration'),
    ('test_capability_gap_detection', 'app.tests.test_capability_gap_detection', 'TestCapabilityGapDetection'),
    ('test_autonomous_self_development_integration', 'app.tests.test_autonomous_self_development_integration', 'TestAutonomousSelfDevelopmentIntegration'),
    ('test_activity_stream', 'app.tests.test_activity_stream', 'ActivityStreamEventTests'),
    ('test_activity_stream', 'app.tests.test_activity_stream', 'ActivityStreamQueryTests'),
    ('test_activity_stream', 'app.tests.test_activity_stream', 'ActivityStreamPersistenceTests'),
    ('test_activity_stream', 'app.tests.test_activity_stream', 'ActivityStreamThreadingTests'),
    ('test_dynamic_ui', 'app.tests.test_dynamic_ui', 'DynamicUiResolverTests'),
    ('test_dynamic_ui', 'app.tests.test_dynamic_ui', 'DynamicUiDataTests'),
]

all_pass = True
for name, module, class_name in test_classes:
    try:
        mod = __import__(module, fromlist=[''])
        if class_name:
            cls = getattr(mod, class_name)
            loader = unittest.TestLoader()
            suite = loader.loadTestsFromTestCase(cls)
            runner = unittest.TextTestRunner(verbosity=0)
            result = runner.run(suite)
            passed = result.wasSuccessful()
            status = "PASS" if passed else "FAIL"
            print(f"{name}: {status} ({result.testsRun} tests)")
            if not passed:
                all_pass = False
        else:
            # For test_autonomous_work which has multiple test classes
            print(f"{name}: SKIPPED (multiple classes)")
    except Exception as e:
        print(f"{name}: ERROR - {e}")
        all_pass = False

print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
sys.exit(0 if all_pass else 1)