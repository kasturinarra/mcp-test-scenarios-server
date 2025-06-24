#!/usr/bin/env python3

import os
from typing import Any, Dict, List, Optional
import pandas as pd
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("microshift-test-analyzer")

# Configuration
GOOGLE_CLIENT_EMAIL = os.getenv('GOOGLE_CLIENT_EMAIL')
GOOGLE_PRIVATE_KEY = os.getenv('GOOGLE_PRIVATE_KEY')
SPREADSHEET_ID = '1FLO4S4-iJeAYVh0BGsgiwKVeTUkpi-Mw7GmEs_zFhlg'


async def get_sheets_data(sheet_name: Optional[str] = None) -> List[List[str]]:
    """Fetch data from Google Sheets."""
    try:
        # Validate required environment variables
        if not GOOGLE_CLIENT_EMAIL or not GOOGLE_PRIVATE_KEY:
            raise ValueError("GOOGLE_CLIENT_EMAIL and GOOGLE_PRIVATE_KEY environment variables must be set")
            
        # Create credentials from environment variables
        credentials_info = {
            "type": "service_account",
            "client_email": GOOGLE_CLIENT_EMAIL,
            "private_key": GOOGLE_PRIVATE_KEY.replace('\\n', '\n') if GOOGLE_PRIVATE_KEY else None,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        
        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
        
        service = build('sheets', 'v4', credentials=credentials)
        sheet = service.spreadsheets()
        
        # Default to current month's sheet if no name is provided
        if not sheet_name:
            now = datetime.now()
            sheet_name = now.strftime('%Y_%m') # e.g., "2025_06"

        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f'{sheet_name}!A:ZZ'
        ).execute()
        
        return result.get('values', [])
    
    except Exception as e:
        raise Exception(f"Failed to fetch Google Sheets data: {str(e)}")


def parse_test_data(raw_data: List[List[str]]) -> pd.DataFrame:
    """Parse the spreadsheet data into a structured format."""
    if not raw_data or len(raw_data) < 1: # Headers are needed
        return pd.DataFrame()

    headers = raw_data[0]
    num_headers = len(headers)
    
    # Create DataFrame from all rows except the header
    df = pd.DataFrame(raw_data[1:])
    
    # Rename columns based on the header row. 
    # If the dataframe has more columns than headers, the extra columns will get default integer names.
    df.columns = headers + [f'extra_col_{i}' for i in range(len(df.columns) - num_headers)]
    
    # Add a parsed date column for filtering
    try:
        # Extracting date part before the first underscore
        df['parsed_date'] = pd.to_datetime(df['date'].str.split('_').str[0], format='%d/%m/%Y', errors='coerce')
    except Exception:
        # Fallback if the 'date' column doesn't exist or has unexpected format
        df['parsed_date'] = pd.NaT
    
    return df


def extract_pipeline_results(row: pd.Series) -> List[Dict[str, Any]]:
    """Extract testing pipeline results from a row."""
    pipeline_results = []
    
    for i, (col_name, value) in enumerate(row.items()):
        if i < 5 or pd.isna(value) or str(value).strip() == '':
            continue
            
        value_str = str(value).strip()
        if not value_str:
            continue
            
        lines = [line.strip() for line in value_str.split('\n') if line.strip()]
        if not lines:
            continue
            
        pipeline_name = col_name
        status = None
        architecture = None
        test_type = None
        framework = None
        failure_reason = None
        
        for j, line in enumerate(lines):
            if line.upper() in ['SUCCESS', 'FAILURE', 'FAILED', 'PASS', 'PASSED']:
                status = line.upper()
                if status in ['FAILED', 'FAILURE']:
                    status = 'FAILURE'
                elif status in ['PASS', 'PASSED', 'SUCCESS']:
                    status = 'SUCCESS'
            elif line in ['x86_64', 'aarch64', 'x86']:
                architecture = line
            elif line in ['RobotFramework', 'Ginkgo']:
                framework = line
            elif 'install' in line.lower() or 'upgrade' in line.lower() or 'ostree' in line.lower() or 'rpm' in line.lower() or 'iso' in line.lower():
                test_type = line
            elif status == 'FAILURE' and j > 0:
                failure_reason = line
        
        pipeline_results.append({
            'pipeline_name': pipeline_name,
            'status': status,
            'architecture': architecture,
            'test_type': test_type,
            'framework': framework,
            'failure_reason': failure_reason,
            'raw_value': value_str
        })
    
    return pipeline_results


@mcp.tool()
async def get_failed_pipelines_by_version(version: Optional[str] = None, limit: int = 50) -> str:
    """Get failed testing pipelines grouped by MicroShift version.

    Args:
        version: Specific MicroShift version to filter (optional)
        limit: Maximum number of results to return
    """
    raw_data = await get_sheets_data()
    df = parse_test_data(raw_data)
    
    if df.empty:
        return "No data available"

    # Filter the entire DataFrame first if a version filter is provided
    if version:
        try:
            # Use the actual column name for robust filtering
            filtered_df = df[df['MicroShift version'].astype(str).str.contains(version, na=False)]
        except KeyError:
            return "Error: 'MicroShift version' column not found in the spreadsheet."
        except Exception as e:
            return f"Error during filtering: {str(e)}"
    else:
        filtered_df = df

    results = {}
    rows_processed = 0
    
    # Iterate over the complete, filtered results
    for _, row in filtered_df.iterrows():
        # Apply the limit to the number of processed rows from the filtered set
        if rows_processed >= limit:
            break

        microshift_version = row.get('MicroShift version', 'unknown')
        
        pipeline_results = extract_pipeline_results(row)
        failed_pipelines = [p for p in pipeline_results if p['status'] == 'FAILURE']
        
        if failed_pipelines:
            if microshift_version not in results:
                results[microshift_version] = {
                    'version': microshift_version,
                    'total_failures': 0,
                    'failed_pipelines': [],
                    'test_dates': []
                }
            
            results[microshift_version]['total_failures'] += len(failed_pipelines)
            results[microshift_version]['failed_pipelines'].extend(failed_pipelines)
            results[microshift_version]['test_dates'].append(row.get('date', 'unknown'))
        
        rows_processed += 1
    
    return f"""Found {len(results)} versions with failures
Total matching rows in sheet: {len(filtered_df)}
Showing results from {rows_processed} rows (limit applied)
Version filter: {version or 'None'}

Results:
{str(results)}"""


@mcp.tool()
async def get_failure_summary(group_by: str = "version") -> str:
    """Get summary of test failures across all MicroShift versions.

    Args:
        group_by: Group failures by 'version', 'pipeline', or 'reason'
    """
    raw_data = await get_sheets_data()
    df = parse_test_data(raw_data)
    
    if df.empty:
        return "No data available"
    
    summary = {
        'total_test_runs': len(df),
        'group_by': group_by,
        'summary_data': {}
    }
    
    all_failures = []
    
    for _, row in df.iterrows():
        pipeline_results = extract_pipeline_results(row)
        failed_pipelines = [p for p in pipeline_results if p['status'] == 'FAILURE']
        
        for failure in failed_pipelines:
            failure['microshift_version'] = row.iloc[4] if len(row) > 4 else 'unknown'
            failure['date'] = row.iloc[0] if len(row) > 0 else 'unknown'
            all_failures.append(failure)
    
    if group_by == "version":
        version_counts = {}
        for failure in all_failures:
            version = failure['microshift_version']
            if version not in version_counts:
                version_counts[version] = 0
            version_counts[version] += 1
        summary['summary_data'] = version_counts
        
    elif group_by == "pipeline":
        pipeline_counts = {}
        for failure in all_failures:
            pipeline = failure['pipeline_name']
            if pipeline not in pipeline_counts:
                pipeline_counts[pipeline] = 0
            pipeline_counts[pipeline] += 1
        summary['summary_data'] = pipeline_counts
        
    elif group_by == "reason":
        reason_counts = {}
        for failure in all_failures:
            reason = failure.get('failure_reason', 'No reason provided')
            if reason not in reason_counts:
                reason_counts[reason] = 0
            reason_counts[reason] += 1
        summary['summary_data'] = reason_counts
    
    summary['total_failures'] = len(all_failures)
    return str(summary)


@mcp.tool()
async def search_failure_reasons(search_term: str, version: Optional[str] = None) -> str:
    """Search for specific failure reasons across all tests.

    Args:
        search_term: Search term to find in failure reasons
        version: Filter by specific MicroShift version (optional)
    """
    raw_data = await get_sheets_data()
    df = parse_test_data(raw_data)
    
    if df.empty:
        return "No data available"
    
    matching_failures = []
    
    for _, row in df.iterrows():
        microshift_version = row.iloc[4] if len(row) > 4 else 'unknown'
        
        if version and version not in str(microshift_version):
            continue
            
        pipeline_results = extract_pipeline_results(row)
        
        for result in pipeline_results:
            if result['status'] == 'FAILURE':
                failure_reason = result.get('failure_reason', '')
                if failure_reason and search_term.lower() in str(failure_reason).lower():
                    matching_failures.append({
                        'date': row.iloc[0] if len(row) > 0 else 'unknown',
                        'microshift_version': microshift_version,
                        'pipeline': result['pipeline_name'],
                        'failure_reason': failure_reason,
                        'architecture': result.get('architecture'),
                        'test_type': result.get('test_type'),
                        'framework': result.get('framework')
                    })
    
    return f"""Search Results:
Search term: {search_term}
Version filter: {version or 'None'}
Total matches: {len(matching_failures)}

Matches:
{str(matching_failures)}"""


@mcp.tool()
async def get_version_comparison(version1: str, version2: str) -> str:
    """Compare test results between different MicroShift versions.

    Args:
        version1: First MicroShift version to compare
        version2: Second MicroShift version to compare
    """
    raw_data = await get_sheets_data()
    df = parse_test_data(raw_data)
    
    if df.empty:
        return "No data available"
    
    version1_data = {'total_tests': 0, 'failures': 0, 'successes': 0, 'pipelines': {}}
    version2_data = {'total_tests': 0, 'failures': 0, 'successes': 0, 'pipelines': {}}
    
    for _, row in df.iterrows():
        microshift_version = row.iloc[4] if len(row) > 4 else 'unknown'
        
        target_data = None
        if version1 in str(microshift_version):
            target_data = version1_data
        elif version2 in str(microshift_version):
            target_data = version2_data
        else:
            continue
        
        pipeline_results = extract_pipeline_results(row)
        
        for result in pipeline_results:
            pipeline = result['pipeline_name']
            status = result['status']
            
            target_data['total_tests'] += 1
            
            if status == 'FAILURE':
                target_data['failures'] += 1
            elif status == 'SUCCESS':
                target_data['successes'] += 1
            
            if pipeline not in target_data['pipelines']:
                target_data['pipelines'][pipeline] = {'total': 0, 'failures': 0, 'successes': 0}
            
            target_data['pipelines'][pipeline]['total'] += 1
            if status == 'FAILURE':
                target_data['pipelines'][pipeline]['failures'] += 1
            elif status == 'SUCCESS':
                target_data['pipelines'][pipeline]['successes'] += 1
    
    for data in [version1_data, version2_data]:
        if data['total_tests'] > 0:
            data['failure_rate'] = (data['failures'] / data['total_tests']) * 100
            data['success_rate'] = (data['successes'] / data['total_tests']) * 100
        else:
            data['failure_rate'] = 0
            data['success_rate'] = 0
    
    better_performer = version1 if version1_data['failure_rate'] < version2_data['failure_rate'] else version2
    
    return f"""Version Comparison:

Version 1: {version1}
- Total tests: {version1_data['total_tests']}
- Failures: {version1_data['failures']}
- Successes: {version1_data['successes']}
- Failure rate: {version1_data['failure_rate']:.2f}%

Version 2: {version2}
- Total tests: {version2_data['total_tests']}
- Failures: {version2_data['failures']}
- Successes: {version2_data['successes']}
- Failure rate: {version2_data['failure_rate']:.2f}%

Better performer: {better_performer}"""


@mcp.tool()
async def get_pipeline_failure_trends(pipeline_name: Optional[str] = None, days: int = 30) -> str:
    """Analyze failure trends for specific testing pipelines over time.

    Args:
        pipeline_name: Name of the testing pipeline to analyze (optional)
        days: Number of days to look back
    """
    raw_data = await get_sheets_data()
    df = parse_test_data(raw_data)
    
    if df.empty:
        return "No data available"
    
    trends = {}
    
    for _, row in df.iterrows():
        pipeline_results = extract_pipeline_results(row)
        
        for result in pipeline_results:
            if pipeline_name and pipeline_name not in result['pipeline_name']:
                continue
                
            pipeline = result['pipeline_name']
            if pipeline not in trends:
                trends[pipeline] = {
                    'total_runs': 0,
                    'failures': 0,
                    'success': 0,
                    'failure_rate': 0.0,
                    'recent_failures': []
                }
            
            trends[pipeline]['total_runs'] += 1
            
            if result['status'] == 'FAILURE':
                trends[pipeline]['failures'] += 1
                trends[pipeline]['recent_failures'].append({
                    'date': row.iloc[0] if len(row) > 0 else 'unknown',
                    'version': row.iloc[4] if len(row) > 4 else 'unknown',
                    'reason': result.get('failure_reason', 'No reason provided')
                })
            elif result['status'] == 'SUCCESS':
                trends[pipeline]['success'] += 1
    
    for pipeline in trends:
        total = trends[pipeline]['total_runs']
        if total > 0:
            trends[pipeline]['failure_rate'] = (trends[pipeline]['failures'] / total) * 100
    
    return f"""Pipeline Failure Trends:
Pipeline filter: {pipeline_name or 'All pipelines'}
Days analyzed: {days}

Trends:
{str(trends)}"""


if __name__ == "__main__":
    mcp.run(transport='stdio')