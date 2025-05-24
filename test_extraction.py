#!/usr/bin/env python3
"""
Test script to verify archive extraction dependencies are working correctly.
"""

def test_py7zr():
    """Test py7zr import and functionality."""
    try:
        import py7zr
        print("✓ py7zr imported successfully")
        print(f"  Version: {py7zr.__version__}")
        return True
    except ImportError as e:
        print(f"✗ py7zr import failed: {e}")
        return False
    except Exception as e:
        print(f"✗ py7zr error: {e}")
        return False

def test_pyunpack():
    """Test pyunpack import and functionality."""
    try:
        from pyunpack import Archive
        print("✓ pyunpack imported successfully")
        
        # Test if pyunpack can find any extractors
        try:
            # This will show what extractors pyunpack can find
            import pyunpack.extractors
            extractors = []
            for extractor in dir(pyunpack.extractors):
                if not extractor.startswith('_'):
                    extractors.append(extractor)
            print(f"  Available extractors: {', '.join(extractors)}")
        except:
            pass
            
        return True
    except ImportError as e:
        print(f"✗ pyunpack import failed: {e}")
        return False
    except Exception as e:
        print(f"✗ pyunpack error: {e}")
        return False

def test_patool():
    """Test patool import and functionality (optional)."""
    try:
        import patool
        print("✓ patool imported successfully")
        print(f"  Version: {patool.__version__}")
        return True
    except ImportError as e:
        print(f"⚠ patool import failed: {e}")
        print("  Note: patool is optional - pyunpack may still work with other backends")
        return False
    except Exception as e:
        print(f"⚠ patool error: {e}")
        return False

def test_rarfile():
    """Test rarfile import and functionality."""
    try:
        import rarfile
        print("✓ rarfile imported successfully")
        print(f"  Version: {rarfile.__version__}")
        
        # Check if unrar tool is available
        if rarfile.UNRAR_TOOL:
            print(f"  UnRAR tool: {rarfile.UNRAR_TOOL}")
        else:
            print("  ⚠ UnRAR tool not found - will fallback to pyunpack for RAR files")
            
        return True
    except ImportError as e:
        print(f"✗ rarfile import failed: {e}")
        return False
    except Exception as e:
        print(f"✗ rarfile error: {e}")
        return False

if __name__ == "__main__":
    print("Testing archive extraction dependencies...")
    print("=" * 50)
    
    results = []
    results.append(test_py7zr())
    results.append(test_pyunpack())
    patool_result = test_patool()  # Don't count this as required
    results.append(test_rarfile())
    
    print("=" * 50)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Results: {passed}/{total} core dependencies working correctly")
    if patool_result:
        print("✓ patool is also available")
    
    if passed >= 3:  # py7zr, pyunpack, rarfile are the minimum needed
        print("✓ Archive extraction should work correctly!")
        print("\nThe application should now be able to handle:")
        print("  - .zip files (native zipfile)")
        print("  - .7z files (py7zr with pyunpack fallback)")
        print("  - .rar files (rarfile with pyunpack fallback)")
        print("\nBoth drag-and-drop and browse button should work for OBSE64 installation.")
    else:
        print("✗ Some critical dependencies are missing")
        print("  You may experience issues with archive extraction") 