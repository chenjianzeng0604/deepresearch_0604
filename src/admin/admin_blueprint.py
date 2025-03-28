import hashlib
import os
from datetime import datetime
from functools import wraps
import json
import threading

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort


admin_bp = Blueprint('admin', __name__, template_folder='../../templates/admin')

# Create a variable for the CrawlerConfigManager but don't initialize it yet
crawler_config_manager = None


def get_crawler_config_manager():
    """Get or initialize the CrawlerConfigManager with error handling"""
    global crawler_config_manager
    if crawler_config_manager is None:
        try:
            from src.admin.crawler_config_manager import CrawlerConfigManager
            crawler_config_manager = CrawlerConfigManager()
        except Exception as e:
            print(f"Error initializing CrawlerConfigManager: {str(e)}")
    return crawler_config_manager


def db_required(f):
    """Decorator to check if database is available"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        manager = get_crawler_config_manager()
        if manager is None:
            flash('数据库连接不可用，请检查MySQL配置', 'danger')
            return render_template('error.html', 
                                 message='数据库连接不可用',
                                 details='请确保MySQL服务正在运行，并且环境变量已正确设置')
        return f(*args, **kwargs)
    return decorated_function


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session or not session['admin_logged_in']:
            return redirect(url_for('admin.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def hash_password(password):
    """Hash the password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    success = None
    
    # 如果用户已登录，直接跳转到控制面板
    if 'admin_logged_in' in session and session['admin_logged_in']:
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Hash the provided password
        hashed_password = hash_password(password)
        
        # Only try to verify if we have a database connection
        manager = get_crawler_config_manager()
        if manager:
            try:
                # Check login credentials
                admin_user = manager.verify_admin_login(username, hashed_password)
                
                if admin_user:
                    session['admin_logged_in'] = True
                    session['admin_id'] = admin_user['id']
                    session['admin_username'] = admin_user['username']
                    
                    # Check if there's a next parameter
                    next_url = request.args.get('next')
                    if next_url:
                        return redirect(next_url)
                    return redirect(url_for('admin.dashboard'))
                else:
                    error = '用户名或密码错误，请重试'
            except Exception as e:
                error = f'登录验证失败: {str(e)}'
        else:
            error = '数据库连接不可用，无法验证登录'
    
    return render_template('login.html', error=error, success=success)


@admin_bp.route('/register', methods=['POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        email = request.form.get('email')
        agree_terms = request.form.get('agree_terms')
        
        # 验证输入
        if not username or not password or not confirm_password or not email:
            flash('所有字段都是必填的', 'danger')
            return redirect(url_for('admin.login'))
        
        if password != confirm_password:
            flash('两次输入的密码不一致', 'danger')
            return redirect(url_for('admin.login'))
        
        if not agree_terms:
            flash('必须同意服务条款才能注册', 'danger')
            return redirect(url_for('admin.login'))
        
        # 哈希密码
        hashed_password = hash_password(password)
        
        # 只有在有数据库连接的情况下才尝试注册
        manager = get_crawler_config_manager()
        if manager:
            try:
                # 检查用户名是否已存在
                if manager.check_admin_username_exists(username):
                    flash('用户名已存在，请选择其他用户名', 'danger')
                    return redirect(url_for('admin.login'))
                
                # 添加新管理员
                admin_id = manager.add_admin_user(
                    username=username,
                    password=hashed_password,
                    email=email,
                    display_name=username,
                    is_active=True
                )
                
                if admin_id:
                    flash('注册成功，请登录', 'success')
                else:
                    flash('注册失败，请稍后再试', 'danger')
                
                return redirect(url_for('admin.login'))
            except Exception as e:
                flash(f'注册时出错: {str(e)}', 'danger')
                return redirect(url_for('admin.login'))
        else:
            flash('数据库连接不可用，无法注册', 'danger')
            return redirect(url_for('admin.login'))
    
    return redirect(url_for('admin.login'))


@admin_bp.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    flash('已成功退出登录', 'success')
    return redirect(url_for('admin.login'))


@admin_bp.route('/')
@login_required
@db_required
def dashboard():
    """管理后台首页"""
    manager = get_crawler_config_manager()
    try:
        stats = {
            'scenario_count': manager.get_scenario_count(),
            'url_format_count': manager.get_url_format_count(),
            'direct_url_count': manager.get_direct_url_count(),
            'scheduled_task_count': manager.get_scheduled_task_count(),
            'active_task_count': manager.get_active_task_count(),
            'default_scenario': manager.get_default_scenario_name()
        }
        
        # Get all scenarios with counts for the dashboard
        scenarios = manager.get_all_scenarios_with_counts()
        
        return render_template('dashboard.html', 
                               active_page='dashboard',
                               stats=stats,
                               scenarios=scenarios)
    except Exception as e:
        flash(f'加载数据时出错: {str(e)}', 'danger')
        return redirect(url_for('admin.index'))


@admin_bp.route('/scenarios')
@login_required
@db_required
def scenarios():
    # Get all scenarios with counts
    manager = get_crawler_config_manager()
    try:
        scenarios = manager.get_all_scenarios_with_counts()
    except Exception as e:
        flash(f'加载场景数据时出错: {str(e)}', 'danger')
        scenarios = []
    
    return render_template('scenarios.html', active_page='scenarios', scenarios=scenarios)


@admin_bp.route('/scenarios/add', methods=['GET', 'POST'])
@login_required
@db_required
def add_scenario():
    errors = {}
    form_data = {}
    
    if request.method == 'POST':
        # 获取表单数据
        name = request.form.get('name', '').strip()
        display_name = request.form.get('display_name', '').strip()
        description = request.form.get('description', '').strip()
        collection_name = request.form.get('collection_name', '').strip()
        is_default = True if request.form.get('is_default') else False
        
        # 保存表单数据用于错误后重新填充
        form_data = {
            'name': name,
            'display_name': display_name,
            'description': description,
            'collection_name': collection_name,
            'is_default': is_default
        }
        
        # 验证数据
        if not name:
            errors['name'] = '场景名称不能为空'
        elif not name.isascii() or not all(c.islower() or c.isdigit() or c == '_' for c in name):
            errors['name'] = '场景名称只能包含小写字母、数字和下划线'
            
        if not display_name:
            errors['display_name'] = '显示名称不能为空'
            
        if not collection_name:
            errors['collection_name'] = 'Milvus集合名称不能为空'
        elif not collection_name.isascii() or not all(c.isupper() or c.isdigit() or c == '_' for c in collection_name):
            errors['collection_name'] = 'Milvus集合名称只能包含大写字母、数字和下划线'
        
        # 如果没有错误，则保存场景
        if not errors:
            try:
                # 检查场景名称是否已存在
                manager = get_crawler_config_manager()
                existing_scenario = manager.get_scenario_by_name(name)
                
                if existing_scenario:
                    errors['name'] = f'场景名称 "{name}" 已存在，请使用其他名称'
                else:
                    # 添加场景到数据库
                    scenario_id = manager.add_scenario(
                        name=name,
                        display_name=display_name,
                        description=description,
                        collection_name=collection_name,
                        is_default=is_default
                    )
                    
                    if scenario_id:
                        # 如果设置为默认场景，记录日志
                        if is_default:
                            manager.set_default_scenario(scenario_id)
                            flash(f'成功添加场景：{display_name}，并设为默认场景', 'success')
                        else:
                            flash(f'成功添加场景：{display_name}', 'success')
                        
                        # 添加成功后，引导用户添加URL格式
                        return redirect(url_for('admin.scenarios'))
                    else:
                        flash('添加场景失败，请稍后再试', 'danger')
            except Exception as e:
                flash(f'添加场景时出错：{str(e)}', 'danger')
    
    # 传递错误和表单数据到模板
    return render_template('scenario_form.html', 
                           active_page='scenarios', 
                           title='添加爬虫场景',
                           errors=errors,
                           form_data=form_data)


@admin_bp.route('/scenarios/edit/<int:scenario_id>', methods=['GET', 'POST'])
@login_required
@db_required
def edit_scenario(scenario_id):
    # 获取场景数据
    manager = get_crawler_config_manager()
    scenario = manager.get_scenario_by_id(scenario_id)
    
    if not scenario:
        flash('找不到指定的场景', 'danger')
        return redirect(url_for('admin.scenarios'))
    
    errors = {}
    form_data = {}
    
    if request.method == 'POST':
        # 获取表单数据
        display_name = request.form.get('display_name', '').strip()
        description = request.form.get('description', '').strip()
        collection_name = request.form.get('collection_name', '').strip()
        is_default = True if request.form.get('is_default') else False
        is_active = True if request.form.get('is_active') else False
        
        # 保存表单数据用于错误后重新填充
        form_data = {
            'display_name': display_name,
            'description': description,
            'collection_name': collection_name,
            'is_default': is_default,
            'is_active': is_active
        }
        
        # 验证数据
        if not display_name:
            errors['display_name'] = '显示名称不能为空'
            
        if not collection_name:
            errors['collection_name'] = 'Milvus集合名称不能为空'
        elif not collection_name.isascii() or not all(c.isupper() or c.isdigit() or c == '_' for c in collection_name):
            errors['collection_name'] = 'Milvus集合名称只能包含大写字母、数字和下划线'
        
        # 如果没有错误，则更新场景
        if not errors:
            try:
                # 更新场景到数据库
                success = manager.update_scenario(
                    scenario_id=scenario_id,
                    display_name=display_name,
                    description=description,
                    collection_name=collection_name,
                    is_default=is_default,
                    is_active=is_active
                )
                
                if success:
                    flash(f'成功更新场景：{display_name}', 'success')
                    return redirect(url_for('admin.scenarios'))
                else:
                    flash('更新场景失败，请稍后再试', 'danger')
            except Exception as e:
                flash(f'更新场景时出错：{str(e)}', 'danger')
    else:
        # GET请求，填充表单数据
        form_data = {
            'display_name': scenario['display_name'],
            'description': scenario['description'],
            'collection_name': scenario['collection_name'],
            'is_default': scenario['is_default'],
            'is_active': scenario['is_active']
        }
    
    # 传递错误和表单数据到模板
    return render_template('scenario_form.html', 
                           active_page='scenarios', 
                           title='编辑爬虫场景',
                           edit_mode=True,
                           scenario=scenario,
                           errors=errors,
                           form_data=form_data)


@admin_bp.route('/scenarios/delete/<int:scenario_id>', methods=['POST'])
@login_required
@db_required
def delete_scenario(scenario_id):
    # Get scenario data
    manager = get_crawler_config_manager()
    scenario = manager.get_scenario_by_id(scenario_id)
    
    if not scenario:
        flash('找不到指定的场景', 'danger')
        return redirect(url_for('admin.scenarios'))
    
    # Check if it's the default scenario
    if scenario.get('is_default'):
        flash('不能删除默认场景', 'danger')
        return redirect(url_for('admin.scenarios'))
    
    try:
        # Delete scenario from database
        result = manager.delete_scenario(scenario_id)
        
        if result:
            flash(f'成功删除场景：{scenario["display_name"]}', 'success')
        else:
            flash('删除场景失败，请稍后再试', 'danger')
    except Exception as e:
        flash(f'删除场景时出错：{str(e)}', 'danger')
    
    return redirect(url_for('admin.scenarios'))


@admin_bp.route('/scenarios/set-default/<int:scenario_id>', methods=['POST'])
@login_required
@db_required
def set_default_scenario(scenario_id):
    """设置默认场景"""
    manager = get_crawler_config_manager()
    
    # 检查场景是否存在
    scenario = manager.get_scenario_by_id(scenario_id)
    if not scenario:
        flash('找不到指定的场景', 'danger')
        return redirect(url_for('admin.scenarios'))
    
    # 设置为默认场景
    try:
        if manager.set_default_scenario(scenario_id):
            flash(f'已将 {scenario["display_name"]} 设为默认场景', 'success')
        else:
            flash('设置默认场景失败，请稍后再试', 'danger')
    except Exception as e:
        flash(f'设置默认场景时出错：{str(e)}', 'danger')
    
    return redirect(url_for('admin.scenarios'))


@admin_bp.route('/scenarios/toggle/<int:scenario_id>', methods=['POST'])
@login_required
@db_required
def toggle_scenario(scenario_id):
    """启用或禁用场景"""
    manager = get_crawler_config_manager()
    
    # 检查场景是否存在
    scenario = manager.get_scenario_by_id(scenario_id)
    if not scenario:
        flash('找不到指定的场景', 'danger')
        return redirect(url_for('admin.scenarios'))
    
    # 切换场景状态
    try:
        current_status = scenario.get('is_active', True)
        new_status = not current_status
        
        if manager.update_scenario(
            scenario_id=scenario_id,
            is_active=new_status
        ):
            status_text = "启用" if new_status else "禁用"
            flash(f'成功{status_text}场景：{scenario["display_name"]}', 'success')
        else:
            flash('更新场景状态失败，请稍后再试', 'danger')
    except Exception as e:
        flash(f'更新场景状态时出错：{str(e)}', 'danger')
    
    return redirect(url_for('admin.scenarios'))


@admin_bp.route('/url-formats')
@login_required
@db_required
def url_formats():
    # Get all URL formats
    manager = get_crawler_config_manager()
    try:
        url_formats = manager.get_all_url_formats_with_scenario()
    except Exception as e:
        flash(f'加载URL格式数据时出错: {str(e)}', 'danger')
        url_formats = []
    
    # Get all scenarios for filtering
    scenarios = manager.get_all_scenarios()
    
    return render_template('url_formats.html', active_page='url_formats', 
                         url_formats=url_formats, scenarios=scenarios)


@admin_bp.route('/url-formats/add', methods=['GET', 'POST'])
@login_required
@db_required
def add_url_format():
    # Get all scenarios
    manager = get_crawler_config_manager()
    scenarios = manager.get_all_scenarios()
    
    # Get all platforms
    platforms = manager.get_all_platforms()
    
    if request.method == 'POST':
        # Get form data
        scenario_id = request.form.get('scenario_id')
        platform = request.form.get('platform')
        url_format = request.form.get('url_format')
        description = request.form.get('description', '')
        
        # Validate data
        if not scenario_id or not platform or not url_format:
            flash('所有必填字段都必须填写', 'danger')
            return render_template('url_format_form.html', active_page='url_formats', 
                                 title='添加搜索URL格式', scenarios=scenarios, platforms=platforms)
        
        try:
            # Add URL format to database
            url_format_id = manager.add_url_format(
                scenario_id=int(scenario_id),
                platform=platform,
                url_format=url_format,
                description=description
            )
            
            if url_format_id:
                flash(f'成功添加搜索URL格式', 'success')
                return redirect(url_for('admin.url_formats'))
            else:
                flash('添加搜索URL格式失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'添加搜索URL格式时出错：{str(e)}', 'danger')
    
    return render_template('url_format_form.html', active_page='url_formats', 
                         title='添加搜索URL格式', scenarios=scenarios, platforms=platforms)


@admin_bp.route('/url-formats/edit/<int:url_format_id>', methods=['GET', 'POST'])
@login_required
@db_required
def edit_url_format(url_format_id):
    # Get URL format data
    manager = get_crawler_config_manager()
    url_format = manager.get_url_format_by_id(url_format_id)
    
    if not url_format:
        flash('找不到指定的搜索URL格式', 'danger')
        return redirect(url_for('admin.url_formats'))
    
    # Get all scenarios
    scenarios = manager.get_all_scenarios()
    
    # Get all platforms
    platforms = manager.get_all_platforms()
    
    if request.method == 'POST':
        # Get form data
        scenario_id = request.form.get('scenario_id')
        platform = request.form.get('platform')
        url_format_str = request.form.get('url_format')
        description = request.form.get('description', '')
        is_active = True if request.form.get('is_active') else False
        
        # 转换为整数，方便比较
        scenario_id = int(scenario_id) if scenario_id else None
        
        # Validate data
        if not scenario_id or not platform or not url_format_str:
            flash('所有必填字段都必须填写', 'danger')
            return render_template('url_format_form.html', active_page='url_formats', 
                                 title='编辑搜索URL格式', url_format=url_format, 
                                 scenarios=scenarios, platforms=platforms, edit_mode=True)
        
        try:
            # 检查场景ID或平台是否已更改
            changed_scenario = scenario_id != url_format['scenario_id']
            changed_platform = platform != url_format['platform']
            
            # 只在场景ID或平台变化时才需要处理潜在的重复问题
            if changed_scenario or changed_platform:
                with manager.connection.cursor() as cursor:
                    # 检查是否存在相同scenario_id和platform的其他记录
                    cursor.execute(
                        """
                        SELECT id 
                        FROM crawler_url_formats 
                        WHERE scenario_id = %s AND platform = %s AND id != %s
                        """, 
                        (scenario_id, platform, url_format_id)
                    )
                    duplicate = cursor.fetchone()
                    
                    if duplicate:
                        # 存在重复记录，先更新当前记录的所有非主键字段
                        cursor.execute(
                            """
                            UPDATE crawler_url_formats
                            SET url_format = %s, description = %s, is_active = %s
                            WHERE id = %s
                            """,
                            (url_format_str, description, is_active, url_format_id)
                        )
                        
                        # 删除重复记录
                        cursor.execute("DELETE FROM crawler_url_formats WHERE id = %s", (duplicate['id'],))
                        
                        # 更新当前记录的scenario_id和platform字段
                        cursor.execute(
                            """
                            UPDATE crawler_url_formats
                            SET scenario_id = %s, platform = %s
                            WHERE id = %s
                            """,
                            (scenario_id, platform, url_format_id)
                        )
                        
                        manager.connection.commit()
                        flash('成功更新搜索URL格式，替换了已存在的记录', 'success')
                        return redirect(url_for('admin.url_formats'))
            
            # 更新当前记录
            with manager.connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE crawler_url_formats
                    SET scenario_id = %s, platform = %s, url_format = %s, description = %s, is_active = %s
                    WHERE id = %s
                    """,
                    (scenario_id, platform, url_format_str, description, is_active, url_format_id)
                )
                affected_rows = cursor.rowcount
                manager.connection.commit()
                
                if affected_rows > 0:
                    flash('成功更新搜索URL格式', 'success')
                    return redirect(url_for('admin.url_formats'))
                else:
                    flash('更新搜索URL格式失败，请稍后再试', 'danger')
                    
        except Exception as e:
            flash(f'更新搜索URL格式时出错：{str(e)}', 'danger')
    
    return render_template('url_format_form.html', active_page='url_formats', 
                         title='编辑搜索URL格式', url_format=url_format, 
                         scenarios=scenarios, platforms=platforms, edit_mode=True)


@admin_bp.route('/url-formats/delete/<int:url_format_id>', methods=['POST'])
@login_required
@db_required
def delete_url_format(url_format_id):
    """删除URL格式"""
    manager = get_crawler_config_manager()
    
    # 获取URL格式信息
    url_format = manager.get_url_format_by_id(url_format_id)
    if not url_format:
        flash('找不到指定的URL格式', 'danger')
        return redirect(url_for('admin.url_formats'))
    
    # 删除URL格式
    try:
        if manager.delete_url_format(url_format_id):
            # 使用platform字段而不是name字段，因为后者可能不存在
            platform_name = url_format.get('platform', '未知平台')
            flash(f'成功删除URL格式：{platform_name}', 'success')
        else:
            flash('删除URL格式失败，请稍后再试', 'danger')
    except Exception as e:
        flash(f'删除URL格式时出错：{str(e)}', 'danger')
    
    return redirect(url_for('admin.url_formats'))


@admin_bp.route('/url-formats/toggle/<int:url_format_id>', methods=['POST'])
@login_required
@db_required
def toggle_url_format(url_format_id):
    """启用或禁用URL格式"""
    manager = get_crawler_config_manager()
    
    # 检查URL格式是否存在
    url_format = manager.get_url_format_by_id(url_format_id)
    if not url_format:
        flash('找不到指定的URL格式', 'danger')
        return redirect(url_for('admin.url_formats'))
    
    # 切换URL格式状态
    try:
        current_status = url_format.get('is_active', True)
        new_status = not current_status
        
        if manager.update_url_format(
            url_format_id=url_format_id,
            is_active=new_status
        ):
            status_text = "启用" if new_status else "禁用"
            # 使用platform字段代替name字段，因为数据库中没有name字段
            platform_name = url_format.get('platform', '未知平台')
            flash(f'成功{status_text} URL格式：{platform_name}', 'success')
        else:
            flash('更新URL格式状态失败，请稍后再试', 'danger')
    except Exception as e:
        flash(f'更新URL格式状态时出错：{str(e)}', 'danger')
    
    return redirect(url_for('admin.url_formats'))


@admin_bp.route('/direct-urls')
@login_required
@db_required
def direct_urls():
    # Get all direct URLs
    manager = get_crawler_config_manager()
    try:
        direct_urls = manager.get_all_direct_urls_with_scenario()
    except Exception as e:
        flash(f'加载直接爬取URL数据时出错: {str(e)}', 'danger')
        direct_urls = []
    
    # Get all scenarios for filtering
    scenarios = manager.get_all_scenarios()
    
    return render_template('direct_urls.html', active_page='direct_urls', 
                         direct_urls=direct_urls, scenarios=scenarios)


@admin_bp.route('/direct-urls/add', methods=['GET', 'POST'])
@login_required
@db_required
def add_direct_url():
    # Get all scenarios
    manager = get_crawler_config_manager()
    scenarios = manager.get_all_scenarios()
    
    if request.method == 'POST':
        # Get form data
        scenario_id = request.form.get('scenario_id')
        url = request.form.get('url')
        description = request.form.get('description', '')
        
        # Validate data
        if not scenario_id or not url:
            flash('所有必填字段都必须填写', 'danger')
            return render_template('direct_url_form.html', active_page='direct_urls', 
                                 title='添加直接爬取URL', scenarios=scenarios)
        
        try:
            # Add direct URL to database
            direct_url_id = manager.add_direct_url(
                scenario_id=int(scenario_id),
                url=url,
                description=description
            )
            
            if direct_url_id:
                flash(f'成功添加直接爬取URL', 'success')
                return redirect(url_for('admin.direct_urls'))
            else:
                flash('添加直接爬取URL失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'添加直接爬取URL时出错：{str(e)}', 'danger')
    
    return render_template('direct_url_form.html', active_page='direct_urls', 
                         title='添加直接爬取URL', scenarios=scenarios)


@admin_bp.route('/direct-urls/edit/<int:direct_url_id>', methods=['GET', 'POST'])
@login_required
@db_required
def edit_direct_url(direct_url_id):
    # Get direct URL data
    manager = get_crawler_config_manager()
    direct_url = manager.get_direct_url_by_id(direct_url_id)
    
    if not direct_url:
        flash('找不到指定的直接爬取URL', 'danger')
        return redirect(url_for('admin.direct_urls'))
    
    # Get all scenarios
    scenarios = manager.get_all_scenarios()
    
    if request.method == 'POST':
        # Get form data
        url = request.form.get('url')
        description = request.form.get('description', '')
        is_active = True if request.form.get('is_active') else False
        
        # Validate data
        if not url:
            flash('所有必填字段都必须填写', 'danger')
            return render_template('direct_url_form.html', active_page='direct_urls', 
                                 title='编辑直接爬取URL', direct_url=direct_url, 
                                 scenarios=scenarios, edit_mode=True)
        
        try:
            # 检查场景是否已更改
            if int(request.form.get('scenario_id')) != direct_url['scenario_id']:
                # 如果场景已更改，需要删除旧记录并创建新记录
                # 先删除旧记录
                manager.delete_direct_url(direct_url_id)
                
                # 创建新记录
                new_direct_url_id = manager.add_direct_url(
                    scenario_id=int(request.form.get('scenario_id')),
                    url=url,
                    description=description
                )
                
                if new_direct_url_id:
                    # 如果需要设置为非活动状态
                    if not is_active:
                        manager.update_direct_url(
                            direct_url_id=new_direct_url_id,
                            is_active=False
                        )
                    flash(f'成功更新直接爬取URL并更改了所属场景', 'success')
                    return redirect(url_for('admin.direct_urls'))
                else:
                    flash('更新直接爬取URL失败，请稍后再试', 'danger')
            else:
                # 如果场景未更改，直接更新其他字段
                result = manager.update_direct_url(
                    direct_url_id=direct_url_id,
                    url=url,
                    description=description,
                    is_active=is_active
                )
                
                if result:
                    flash(f'成功更新直接爬取URL', 'success')
                    return redirect(url_for('admin.direct_urls'))
                else:
                    flash('更新直接爬取URL失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'更新直接爬取URL时出错：{str(e)}', 'danger')
    
    return render_template('direct_url_form.html', active_page='direct_urls', 
                         title='编辑直接爬取URL', direct_url=direct_url, 
                         scenarios=scenarios, edit_mode=True)


@admin_bp.route('/direct-urls/delete/<int:direct_url_id>', methods=['POST'])
@login_required
@db_required
def delete_direct_url(direct_url_id):
    """删除直接爬取URL"""
    manager = get_crawler_config_manager()
    
    # 获取直接URL信息
    direct_url = manager.get_direct_url_by_id(direct_url_id)
    if not direct_url:
        flash('找不到指定的直接爬取URL', 'danger')
        return redirect(url_for('admin.direct_urls'))
    
    # 删除直接URL
    try:
        if manager.delete_direct_url(direct_url_id):
            flash(f'成功删除直接爬取URL', 'success')
        else:
            flash('删除直接爬取URL失败，请稍后再试', 'danger')
    except Exception as e:
        flash(f'删除直接爬取URL时出错：{str(e)}', 'danger')
    
    return redirect(url_for('admin.direct_urls'))


@admin_bp.route('/direct-urls/toggle/<int:direct_url_id>', methods=['POST'])
@login_required
@db_required
def toggle_direct_url(direct_url_id):
    """启用或禁用直接爬取URL"""
    manager = get_crawler_config_manager()
    
    # 检查直接URL是否存在
    direct_url = manager.get_direct_url_by_id(direct_url_id)
    if not direct_url:
        flash('找不到指定的直接爬取URL', 'danger')
        return redirect(url_for('admin.direct_urls'))
    
    # 切换直接URL状态
    try:
        current_status = direct_url.get('is_active', True)
        new_status = not current_status
        
        if manager.update_direct_url(
            direct_url_id=direct_url_id,
            is_active=new_status
        ):
            status_text = "启用" if new_status else "禁用"
            title = direct_url.get('title', '未命名URL')
            flash(f'成功{status_text}直接爬取URL：{title}', 'success')
        else:
            flash('更新直接爬取URL状态失败，请稍后再试', 'danger')
    except Exception as e:
        flash(f'更新直接爬取URL状态时出错：{str(e)}', 'danger')
    
    return redirect(url_for('admin.direct_urls'))


@admin_bp.route('/platforms')
@login_required
@db_required
def platforms():
    # Get all platforms
    manager = get_crawler_config_manager()
    try:
        platforms = manager.get_all_platforms()
    except Exception as e:
        flash(f'加载平台数据时出错: {str(e)}', 'danger')
        platforms = []
    
    return render_template('platforms.html', active_page='platforms', platforms=platforms)


@admin_bp.route('/platforms/add', methods=['GET', 'POST'])
@login_required
@db_required
def add_platform():
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        display_name = request.form.get('display_name')
        description = request.form.get('description', '')
        
        # Validate data
        if not name or not display_name:
            flash('所有必填字段都必须填写', 'danger')
            return render_template('platform_form.html', active_page='platforms', title='添加平台')
        
        try:
            # Add platform to database
            manager = get_crawler_config_manager()
            platform_id = manager.add_platform(
                name=name,
                display_name=display_name,
                description=description
            )
            
            if platform_id:
                flash(f'成功添加平台：{display_name}', 'success')
                return redirect(url_for('admin.platforms'))
            else:
                flash('添加平台失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'添加平台时出错：{str(e)}', 'danger')
    
    return render_template('platform_form.html', active_page='platforms', title='添加平台')


@admin_bp.route('/platforms/edit/<int:platform_id>', methods=['GET', 'POST'])
@login_required
@db_required
def edit_platform(platform_id):
    # Get platform data
    manager = get_crawler_config_manager()
    platform = manager.get_platform_by_id(platform_id)
    
    if not platform:
        flash('找不到指定的平台', 'danger')
        return redirect(url_for('admin.platforms'))
    
    if request.method == 'POST':
        # Get form data
        display_name = request.form.get('display_name')
        description = request.form.get('description', '')
        is_active = True if request.form.get('is_active') else False
        
        # Validate data
        if not display_name:
            flash('所有必填字段都必须填写', 'danger')
            return render_template('platform_form.html', active_page='platforms', 
                                 title='编辑平台', platform=platform, edit_mode=True)
        
        try:
            # Update platform in database
            result = manager.update_platform(
                platform_id=platform_id,
                display_name=display_name,
                description=description,
                is_active=is_active
            )
            
            if result:
                flash(f'成功更新平台：{display_name}', 'success')
                return redirect(url_for('admin.platforms'))
            else:
                flash('更新平台失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'更新平台时出错：{str(e)}', 'danger')
    
    return render_template('platform_form.html', active_page='platforms', 
                         title='编辑平台', platform=platform, edit_mode=True)


@admin_bp.route('/platforms/delete/<int:platform_id>', methods=['POST'])
@login_required
@db_required
def delete_platform(platform_id):
    """删除平台"""
    manager = get_crawler_config_manager()
    
    # 检查平台是否存在
    platform = manager.get_platform_by_id(platform_id)
    if not platform:
        flash('找不到指定的平台', 'danger')
        return redirect(url_for('admin.platforms'))
    
    # 删除平台
    try:
        if manager.delete_platform(platform_id):
            flash(f'成功删除平台：{platform["display_name"]}', 'success')
        else:
            flash('删除平台失败，请稍后再试', 'danger')
    except Exception as e:
        flash(f'删除平台时出错：{str(e)}', 'danger')
    
    return redirect(url_for('admin.platforms'))


@admin_bp.route('/platforms/toggle/<int:platform_id>', methods=['POST'])
@login_required
@db_required
def toggle_platform(platform_id):
    """启用或禁用平台"""
    manager = get_crawler_config_manager()
    
    # 检查平台是否存在
    platform = manager.get_platform_by_id(platform_id)
    if not platform:
        flash('找不到指定的平台', 'danger')
        return redirect(url_for('admin.platforms'))
    
    # 切换平台状态
    try:
        current_status = platform.get('is_active', True)
        new_status = not current_status
        
        if manager.update_platform(
            platform_id=platform_id,
            is_active=new_status
        ):
            status_text = "启用" if new_status else "禁用"
            flash(f'成功{status_text}平台：{platform["display_name"]}', 'success')
        else:
            flash('更新平台状态失败，请稍后再试', 'danger')
    except Exception as e:
        flash(f'更新平台状态时出错：{str(e)}', 'danger')
    
    return redirect(url_for('admin.platforms'))


# 定时爬虫任务管理路由
@admin_bp.route('/scheduled_tasks')
@login_required
@db_required
def scheduled_tasks():
    """定时爬虫任务管理页面"""
    manager = get_crawler_config_manager()
    tasks = manager.get_all_scheduled_tasks()
    scenarios = manager.get_all_scenarios()
    platforms = manager.get_all_platforms()
    
    # 解析JSON格式的关键词和平台
    for task in tasks:
        if task.get('keywords'):
            try:
                task['keywords_list'] = json.loads(task['keywords'])
            except:
                task['keywords_list'] = []
        else:
            task['keywords_list'] = []
            
        if task.get('platforms'):
            try:
                task['platforms_list'] = json.loads(task['platforms'])
            except:
                task['platforms_list'] = []
        else:
            task['platforms_list'] = []
    
    return render_template('scheduled_tasks.html', 
                           active_page='scheduled_tasks', 
                           tasks=tasks,
                           scenarios=scenarios,
                           platforms=platforms)


@admin_bp.route('/scheduled_tasks/add', methods=['GET', 'POST'])
@login_required
@db_required
def add_scheduled_task():
    """添加定时爬虫任务"""
    manager = get_crawler_config_manager()
    scenarios = manager.get_all_scenarios()
    platforms = manager.get_all_platforms()
    
    if request.method == 'POST':
        # 获取表单数据
        task_name = request.form.get('task_name')
        scenario_id = request.form.get('scenario_id')
        keywords_str = request.form.get('keywords', '')
        selected_platforms = request.form.getlist('selected_platforms')
        cron_expression = request.form.get('cron_expression')
        max_concurrent_tasks = request.form.get('max_concurrent_tasks', 3)
        description = request.form.get('description', '')
        is_active = 'is_active' in request.form
        
        # 验证数据
        if not task_name or not scenario_id or not keywords_str or not cron_expression:
            flash('所有必填字段都必须填写', 'danger')
            return render_template('scheduled_task_form.html', 
                                  active_page='scheduled_tasks',
                                  title='添加定时爬虫任务',
                                  scenarios=scenarios,
                                  platforms=platforms)
        
        try:
            # 处理关键词列表
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
            
            # 处理平台列表
            selected_platforms = request.form.getlist('selected_platforms')
            
            # 检查是否选择了平台
            if not selected_platforms:
                flash('请至少选择一个平台', 'danger')
                return render_template('scheduled_task_form.html', 
                                      active_page='scheduled_tasks',
                                      title='添加定时爬虫任务',
                                      scenarios=scenarios,
                                      platforms=platforms)
            
            # 添加任务到数据库
            task_id = manager.add_scheduled_task(
                task_name=task_name,
                scenario_id=scenario_id,
                keywords=keywords,
                platforms=selected_platforms,
                cron_expression=cron_expression,
                max_concurrent_tasks=int(max_concurrent_tasks),
                description=description,
                is_active=is_active
            )
            
            if task_id:
                flash(f'成功添加定时爬虫任务：{task_name}', 'success')
                return redirect(url_for('admin.scheduled_tasks'))
            else:
                flash('添加定时爬虫任务失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'添加定时爬虫任务时出错：{str(e)}', 'danger')
    
    return render_template('scheduled_task_form.html', 
                          active_page='scheduled_tasks',
                          title='添加定时爬虫任务',
                          scenarios=scenarios,
                          platforms=platforms)


@admin_bp.route('/scheduled_tasks/edit/<int:task_id>', methods=['GET', 'POST'])
@login_required
@db_required
def edit_scheduled_task(task_id):
    """编辑定时爬虫任务"""
    # 获取任务数据
    manager = get_crawler_config_manager()
    task = manager.get_scheduled_task(task_id)
    scenarios = manager.get_all_scenarios()
    platforms = manager.get_all_platforms()
    
    if not task:
        flash('找不到指定的定时爬虫任务', 'danger')
        return redirect(url_for('admin.scheduled_tasks'))
    
    # 解析JSON格式的关键词和平台
    if task.get('keywords'):
        try:
            task['keywords_list'] = json.loads(task['keywords'])
            task['keywords_str'] = ', '.join(task['keywords_list'])
        except:
            task['keywords_list'] = []
            task['keywords_str'] = ''
    else:
        task['keywords_list'] = []
        task['keywords_str'] = ''
        
    if task.get('platforms'):
        try:
            task['platforms_list'] = json.loads(task['platforms'])
        except:
            task['platforms_list'] = []
    else:
        task['platforms_list'] = []
    
    if request.method == 'POST':
        # 获取表单数据
        task_name = request.form.get('task_name')
        scenario_id = request.form.get('scenario_id')
        keywords_str = request.form.get('keywords', '')
        cron_expression = request.form.get('cron_expression')
        max_concurrent_tasks = request.form.get('max_concurrent_tasks', 3)
        description = request.form.get('description', '')
        is_active = 'is_active' in request.form
        
        # 验证数据
        if not task_name or not scenario_id or not keywords_str or not cron_expression:
            flash('所有必填字段都必须填写', 'danger')
            return render_template('scheduled_task_form.html', 
                                  active_page='scheduled_tasks',
                                  title='编辑定时爬虫任务',
                                  task=task,
                                  edit_mode=True,
                                  scenarios=scenarios,
                                  platforms=platforms)
        
        try:
            # 处理关键词列表
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
            
            # 处理平台列表
            selected_platforms = request.form.getlist('selected_platforms')
            
            # 检查是否选择了平台
            if not selected_platforms:
                flash('请至少选择一个平台', 'danger')
                return render_template('scheduled_task_form.html', 
                                      active_page='scheduled_tasks',
                                      title='编辑定时爬虫任务',
                                      task=task,
                                      edit_mode=True,
                                      scenarios=scenarios,
                                      platforms=platforms)
            
            # 更新任务
            success = manager.update_scheduled_task(
                task_id=task_id,
                task_name=task_name,
                scenario_id=scenario_id,
                keywords=keywords,
                platforms=selected_platforms,
                cron_expression=cron_expression,
                max_concurrent_tasks=int(max_concurrent_tasks),
                description=description,
                is_active=is_active
            )
            
            if success:
                flash(f'成功更新定时爬虫任务：{task_name}', 'success')
                return redirect(url_for('admin.scheduled_tasks'))
            else:
                flash('更新定时爬虫任务失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'更新定时爬虫任务时出错：{str(e)}', 'danger')
    
    return render_template('scheduled_task_form.html', 
                          active_page='scheduled_tasks',
                          title='编辑定时爬虫任务',
                          task=task,
                          edit_mode=True,
                          scenarios=scenarios,
                          platforms=platforms)


@admin_bp.route('/scheduled_tasks/delete/<int:task_id>', methods=['POST'])
@login_required
@db_required
def delete_scheduled_task(task_id):
    """删除定时爬虫任务"""
    manager = get_crawler_config_manager()
    
    # 获取任务信息（用于日志记录）
    task = manager.get_scheduled_task(task_id)
    if not task:
        flash('找不到指定的定时爬虫任务', 'danger')
        return redirect(url_for('admin.scheduled_tasks'))
    
    # 执行删除操作
    success = manager.delete_scheduled_task(task_id)
    
    if success:
        flash(f'成功删除定时爬虫任务：{task["task_name"]}', 'success')
    else:
        flash('删除定时爬虫任务失败，请稍后再试', 'danger')
    
    return redirect(url_for('admin.scheduled_tasks'))


@admin_bp.route('/scheduled_tasks/toggle/<int:task_id>', methods=['POST'])
@login_required
@db_required
def toggle_scheduled_task(task_id):
    """切换定时爬虫任务的启用状态"""
    manager = get_crawler_config_manager()
    
    # 获取任务信息（用于日志和消息）
    task = manager.get_scheduled_task(task_id)
    if not task:
        flash('找不到指定的定时爬虫任务', 'danger')
        return redirect(url_for('admin.scheduled_tasks'))
    
    # 执行状态切换
    success = manager.toggle_scheduled_task_status(task_id)
    
    if success:
        new_status = not task['is_active']
        status_text = '启用' if new_status else '禁用'
        flash(f'成功{status_text}定时爬虫任务：{task["task_name"]}', 'success')
    else:
        flash('切换定时爬虫任务状态失败，请稍后再试', 'danger')
    
    return redirect(url_for('admin.scheduled_tasks'))


@admin_bp.route('/scheduled_tasks/run/<int:task_id>', methods=['GET', 'POST'])
@login_required
@db_required
def run_scheduled_task(task_id):
    """立即执行定时爬虫任务"""
    manager = get_crawler_config_manager()
    
    # 获取任务信息
    task = manager.get_scheduled_task(task_id)
    if not task:
        flash('找不到指定的定时爬虫任务', 'danger')
        return redirect(url_for('admin.scheduled_tasks'))
    
    try:
        # 解析任务参数
        keywords = json.loads(task['keywords'])
        platforms = json.loads(task['platforms'])
        scenario = task['scenario_name']
        
        # 更新最后运行时间
        manager.update_task_last_run_time(task_id)
        
        # 异步执行爬虫任务
        async def run_crawler_task():
            from src.tools.crawler.scheduled_crawler import ScheduledCrawler
            crawler = ScheduledCrawler()
            await crawler.run_task_by_id(task_id)
            
        # 在后台线程中运行异步任务
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        def run_background_task():
            loop.run_until_complete(run_crawler_task())
            loop.close()
            
        thread = threading.Thread(target=run_background_task)
        thread.daemon = True
        thread.start()
        
        flash(f'已启动定时爬虫任务：{task["task_name"]}，正在后台执行...', 'success')
    except Exception as e:
        flash(f'执行定时爬虫任务时出错：{str(e)}', 'danger')
    
    return redirect(url_for('admin.scheduled_tasks'))


# Initialize admin user if none exists
@admin_bp.before_app_first_request
def initialize_admin():
    try:
        # This is now handled by init_crawler_default_data in crawler_schema.py
        # Just verify that the connection is working properly
        manager = get_crawler_config_manager()
        if manager:
            print("Admin initialization complete - database connection confirmed.")
    except Exception as e:
        print(f"Error initializing admin user: {str(e)}")
