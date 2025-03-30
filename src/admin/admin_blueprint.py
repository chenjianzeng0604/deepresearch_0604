
from pathlib import Path
import sys

FILE_PATH = Path(__file__).resolve()
ROOT_DIR = FILE_PATH.parent.parent.parent
sys.path.append(str(ROOT_DIR))  # 将项目根目录添加到Python路径

from flask import render_template, redirect, url_for, flash, request, session, Blueprint
from src.admin.crawler_config_manager import crawler_config_manager
from src.utils.auth_utils import login_required
from src.utils.auth_utils import db_required as create_db_required

from src.utils.log_utils import setup_logging
logger = setup_logging(app_name="app")

db_required = create_db_required(crawler_config_manager)

admin = Blueprint('admin', __name__, template_folder='../../templates/admin')

# 根路由 - 重定向到管理登录页面
@admin.route('/')
def root_index():
    """重定向到管理登录页面"""
    return redirect(url_for('admin.login'))

# 错误处理
@admin.errorhandler(404)
def page_not_found(e):
    """404页面"""
    return render_template('admin/error.html', error="页面不存在", message="找不到请求的页面"), 404

@admin.errorhandler(500)
def server_error(e):
    """500页面"""
    return render_template('admin/error.html', error="服务器内部错误", message="服务器处理请求时发生错误"), 500

# ====================== 管理员登录相关路由 ======================
@admin.route('/login', methods=['GET', 'POST'])
def login():
    """管理员登录"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('请输入用户名和密码', 'danger')
            return render_template('admin/login.html')
            
        if not crawler_config_manager:
            flash('数据库连接不可用，请联系系统管理员', 'danger')
            return render_template('admin/login.html')
        
        user = crawler_config_manager.verify_admin_login(username, password)
        if user:
            # 登录成功，设置会话
            session['admin_logged_in'] = True
            session['admin_id'] = user['id']
            session['admin_username'] = user['username']
            
            flash(f'欢迎回来，{user["username"]}!', 'success')
            
            # 重定向到之前尝试访问的页面，或默认到管理首页
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/admin'):
                return redirect(next_page)
            return redirect(url_for('admin.dashboard'))
        else:
            flash('用户名或密码错误', 'danger')
            
    return render_template('admin/login.html')

@admin.route('/register', methods=['GET', 'POST'])
def register():
    """管理员注册"""
    # 检查是否已有管理员账户
    if not crawler_config_manager:
        flash('数据库连接不可用，请联系系统管理员', 'danger')
        return render_template('admin/register.html')
        
    try:
        # 检查是否已存在管理员账户
        with crawler_config_manager.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM crawler_admin_users")
            admin_count = cursor.fetchone()['count']
            
            # 如果已有管理员，则重定向到登录页面
            if admin_count > 0 and 'admin_logged_in' not in session:
                flash('已有管理员账户，请登录', 'warning')
                return redirect(url_for('admin.login'))
    except Exception as e:
        logger.error(f"查询管理员账户失败: {str(e)}")
        flash('数据库查询失败，请联系系统管理员', 'danger')
        return render_template('admin/register.html')
        
    # 处理注册表单
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        email = request.form.get('email', '')
        
        # 基本验证
        if not username or not password:
            flash('请输入用户名和密码', 'danger')
            return render_template('admin/register.html')
            
        if password != confirm_password:
            flash('两次输入的密码不一致', 'danger')
            return render_template('admin/register.html')
        
        # 注册新管理员
        user_id = crawler_config_manager.register_admin(username, password, email)
        if user_id:
            flash('注册成功，请登录', 'success')
            return redirect(url_for('admin.login'))
        else:
            flash('注册失败，请稍后再试', 'danger')
            
    return render_template('admin/register.html')

@admin.route('/logout')
def logout():
    """管理员登出"""
    session.pop('admin_logged_in', None)
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    flash('您已成功退出登录', 'success')
    return redirect(url_for('admin.login'))

# ====================== 管理后台路由 ======================
@admin.route('/dashboard')
@login_required
@db_required
def dashboard():
    """管理后台首页"""
    if not crawler_config_manager:
        flash('数据库连接不可用，请联系系统管理员', 'danger')
        return redirect(url_for('admin.login'))
    
    # 获取统计数据
    stats = {
        'scenarios': 0,
        'platforms': 0,
        'url_formats': 0,
        'direct_urls': 0,
        'scheduled_tasks': 0
    }
    
    try:
        with crawler_config_manager.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM crawler_scenarios")
            stats['scenarios'] = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM crawler_platforms")
            stats['platforms'] = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM crawler_url_formats")
            stats['url_formats'] = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM crawler_direct_urls")
            stats['direct_urls'] = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM crawler_scheduled_tasks")
            stats['scheduled_tasks'] = cursor.fetchone()['count']
    except Exception as e:
        logger.error(f"获取统计数据失败: {str(e)}")
        flash('获取统计数据失败', 'danger')
        
    return render_template('admin/dashboard.html', stats=stats)

# 场景管理路由
@admin.route('/scenarios')
@login_required
@db_required
def admin_scenarios():
    # Get all scenarios with counts
    if not crawler_config_manager:
        flash('数据库连接不可用，请联系系统管理员', 'danger')
        return redirect(url_for('admin.login'))
    
    try:
        scenarios = crawler_config_manager.get_all_scenarios_with_counts()
    except Exception as e:
        flash(f'加载场景数据时出错: {str(e)}', 'danger')
        scenarios = []
    
    return render_template('admin/scenarios.html', active_page='scenarios', scenarios=scenarios)

@admin.route('/scenarios/add', methods=['GET', 'POST'])
@login_required
@db_required
def admin_add_scenario():
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
                if not crawler_config_manager:
                    flash('数据库连接不可用，请联系系统管理员', 'danger')
                    return redirect(url_for('admin.scenarios'))
                
                existing_scenario = crawler_config_manager.get_scenario_by_name(name)
                
                if existing_scenario:
                    errors['name'] = f'场景名称 "{name}" 已存在，请使用其他名称'
                else:
                    # 添加场景到数据库
                    scenario_id = crawler_config_manager.add_scenario(
                        name=name,
                        display_name=display_name,
                        description=description,
                        collection_name=collection_name,
                        is_default=is_default
                    )
                    
                    if scenario_id:
                        # 如果设置为默认场景，记录日志
                        if is_default:
                            crawler_config_manager.set_default_scenario(scenario_id)
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
    return render_template('admin/scenario_form.html', 
                            active_page='scenarios', 
                            title='添加爬虫场景',
                            errors=errors,
                            form_data=form_data)

@admin.route('/scenarios/edit/<int:scenario_id>', methods=['GET', 'POST'])
@login_required
@db_required
def admin_edit_scenario(scenario_id):
    # 获取场景数据
    if not crawler_config_manager:
        flash('数据库连接不可用，请联系系统管理员', 'danger')
        return redirect(url_for('admin.scenarios'))
    
    scenario = crawler_config_manager.get_scenario_by_id(scenario_id)
    
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
                success = crawler_config_manager.update_scenario(
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
    return render_template('admin/scenario_form.html', 
                            active_page='scenarios', 
                            title='编辑爬虫场景',
                            edit_mode=True,
                            scenario=scenario,
                            errors=errors,
                            form_data=form_data)

@admin.route('/scenarios/delete/<int:scenario_id>', methods=['POST'])
@login_required
@db_required
def admin_delete_scenario(scenario_id):
    # Get scenario data
    if not crawler_config_manager:
        flash('数据库连接不可用，请联系系统管理员', 'danger')
        return redirect(url_for('admin.scenarios'))
    
    scenario = crawler_config_manager.get_scenario_by_id(scenario_id)
    
    if not scenario:
        flash('找不到指定的场景', 'danger')
        return redirect(url_for('admin.scenarios'))
    
    # Check if it's the default scenario
    if scenario.get('is_default'):
        flash('不能删除默认场景', 'danger')
        return redirect(url_for('admin.scenarios'))
    
    try:
        # Delete scenario from database
        result = crawler_config_manager.delete_scenario(scenario_id)
        
        if result:
            flash(f'成功删除场景：{scenario["display_name"]}', 'success')
        else:
            flash('删除场景失败，请稍后再试', 'danger')
    except Exception as e:
        flash(f'删除场景时出错：{str(e)}', 'danger')
    
    return redirect(url_for('admin.scenarios'))


@admin.route('/scenarios/set-default/<int:scenario_id>', methods=['POST'])
@login_required
@db_required
def admin_set_default_scenario(scenario_id):
    """设置默认场景"""
    if not crawler_config_manager:
        flash('数据库连接不可用，请联系系统管理员', 'danger')
        return redirect(url_for('admin.scenarios'))
    
    # 检查场景是否存在
    scenario = crawler_config_manager.get_scenario_by_id(scenario_id)
    if not scenario:
        flash('找不到指定的场景', 'danger')
        return redirect(url_for('admin.scenarios'))
    
    # 设置为默认场景
    try:
        if crawler_config_manager.set_default_scenario(scenario_id):
            flash(f'已将 {scenario["display_name"]} 设为默认场景', 'success')
        else:
            flash('设置默认场景失败，请稍后再试', 'danger')
    except Exception as e:
        flash(f'设置默认场景时出错：{str(e)}', 'danger')
    
    return redirect(url_for('admin.scenarios'))


@admin.route('/scenarios/toggle/<int:scenario_id>', methods=['POST'])
@login_required
@db_required
def admin_toggle_scenario(scenario_id):
    """启用或禁用场景"""
    if not crawler_config_manager:
        flash('数据库连接不可用，请联系系统管理员', 'danger')
        return redirect(url_for('admin.scenarios'))
    
    # 检查场景是否存在
    scenario = crawler_config_manager.get_scenario_by_id(scenario_id)
    if not scenario:
        flash('找不到指定的场景', 'danger')
        return redirect(url_for('admin.scenarios'))
    
    # 切换场景状态
    try:
        current_status = scenario.get('is_active', True)
        new_status = not current_status
        
        if crawler_config_manager.update_scenario(
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

# 用户管理相关路由
@admin.route('/users')
@login_required
@db_required
def admin_users_list():
    """用户管理页面 - 显示所有用户列表"""
    if not crawler_config_manager:
        flash('数据库连接不可用，请联系系统管理员', 'danger')
        return redirect(url_for('admin.users'))
    
    try:
        users = crawler_config_manager.get_all_admin_users()
        return render_template('admin/users.html', active_page='users', users=users)
    except Exception as e:
        flash(f'加载用户数据时出错: {str(e)}', 'danger')
        return redirect(url_for('admin.users'))